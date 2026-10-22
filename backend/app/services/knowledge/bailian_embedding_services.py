"""调用百炼融合向量接口生成统一的1024维向量。

入库阶段由knowledge_ingestion_services调用；查询阶段由knowledge_retrieval_services调用。
本文件只负责外部HTTP协议、输入校验和响应解析，不负责数据库读写。
"""

import asyncio
import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any

import httpx
from fastapi import status

from app.core.errors import BusinessException
from app.core.settings import get_settings
from app.services.ai import ai_provider_services, ai_usage_services
from app.services.ai.providers.bailian import resolve_dashscope_base

settings = get_settings()
logger = logging.getLogger(__name__)

# 官方HTTP路径固定接在 DashScope /api/v1 后面。
# 端点：POST /api/v1/services/embeddings/multimodal-embedding/multimodal-embedding
MULTIMODAL_EMBEDDING_PATH = "/services/embeddings/multimodal-embedding/multimodal-embedding"


def _read_image_as_data_uri(image_path: Path) -> str:
    """读取私有图片并转换为百炼支持的Base64 Data URI。"""

    if not image_path.is_file():
        raise ValueError(f"图片文件不存在：{image_path.name}")

    # 根据扩展名推测图片MIME；无法识别时拒绝，不把任意二进制伪装成图片。
    mime_type, _ = mimetypes.guess_type(image_path.name)
    if mime_type not in {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/bmp",
        "image/tiff",
    }:
        raise ValueError(f"不支持的图片类型：{image_path.suffix.lower() or '无后缀'}")

    image_bytes = image_path.read_bytes()

    # qwen3-vl-embedding官方限制单张图片不超过10MB。
    if len(image_bytes) > 10 * 1024 * 1024:
        raise ValueError("用于融合向量的单张图片不能超过10MiB")

    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_embedding(response_data: dict[str, Any]) -> list[float]:
    """从百炼JSON中提取唯一融合向量并验证维度。"""

    # 百炼返回层级是output.embeddings[0].embedding。
    # 不直接链式索引，是为了把字段缺失统一转换成可理解的ValueError。
    try:
        embeddings = response_data["output"]["embeddings"]
        embedding = embeddings[0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("百炼Embedding响应缺少预期字段") from exc

    # enable_fusion=true时，文字和图片应融合为唯一向量，而不是分别返回多个向量。
    if len(embeddings) != 1:
        raise ValueError("融合向量接口没有返回唯一向量")

    if not isinstance(embedding, list):
        raise ValueError("百炼Embedding响应中的向量格式错误")

    if len(embedding) != settings.BAILIAN_EMBEDDING_DIMENSION:
        raise ValueError(
            "百炼返回的向量维度与数据库配置不一致："
            f"expected={settings.BAILIAN_EMBEDDING_DIMENSION}, actual={len(embedding)}"
        )

    # 转成float，确保写入pgvector前不存在字符串等意外类型。
    return [float(value) for value in embedding]


async def create_fused_embedding(
    *,
    text: str | None = None,
    image_path: Path | None = None,
) -> list[float]:
    """将文字、图片或二者融合为一个1024维向量。

    调用方式：
    - 纯文字Chunk：只传text；
    - 图文Chunk：同时传text和image_path；
    - 纯图片查询：只传image_path。
    """

    # 去掉文字首尾空白；只传空格不能算有效的纯文字输入。
    normalized_text = text.strip() if text else ""
    if not normalized_text and image_path is None:
        raise ValueError("生成融合向量时，文字和图片不能同时为空")

    # 从能力配置读取（数据库优先，.env回退）。融合向量是百炼专有接口。
    config = await ai_provider_services.get_capability_config(None, "embedding")
    if config is None or not config.api_key:
        raise ai_provider_services.CapabilityNotConfiguredError(
            capability="embedding",
            message="多模态向量服务尚未配置，请联系管理员！Ovo!",
        )

    # contents中的所有元素会在enable_fusion=true时合并成一个向量。
    contents: list[dict[str, str]] = []
    if normalized_text:
        contents.append({"text": normalized_text})

    if image_path is not None:
        # Path.read_bytes是同步磁盘I/O，放入线程避免阻塞事件循环。
        image_data_uri = await asyncio.to_thread(_read_image_as_data_uri, image_path)
        contents.append({"image": image_data_uri})

    # contents允许只有text、只有image，或者二者同时存在。
    # parameters.enable_fusion要求服务端最终只返回一个共同向量。
    request_body = {
        "model": config.model,
        "input": {"contents": contents},
        "parameters": {
            "enable_fusion": True,
            "dimension": settings.BAILIAN_EMBEDDING_DIMENSION,
        },
    }

    url = (
        resolve_dashscope_base(config.base_url, config.dashscope_base_url)
        + MULTIMODAL_EMBEDDING_PATH
    )

    try:
        async with httpx.AsyncClient(
            timeout=config.timeout_seconds,
        ) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": ("Bearer " + config.api_key),
                    "Content-Type": "application/json",
                },
                json=request_body,
            )
            # 4xx/5xx在这里转换成HTTPStatusError，进入下面的安全异常处理。
            response.raise_for_status()

            # 只有成功响应才解析JSON；完整响应不会写入日志，避免泄露知识正文或Base64图片。
            response_data = response.json()
    except httpx.HTTPStatusError as exc:
        # 不记录请求头、Base64图片或完整请求体，避免泄露Key和业务资料。
        provider_request_id = exc.response.headers.get("x-request-id", "-")
        logger.exception(
            "bailian embedding returned error status=%s provider_request_id=%s",
            exc.response.status_code,
            provider_request_id,
        )
        raise BusinessException(
            message="知识库向量服务暂时不可用，请稍后重试！Ovo!",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from None
    except httpx.RequestError:
        logger.exception("bailian embedding network request failed")
        raise BusinessException(
            message="知识库向量服务暂时不可用，请稍后重试！Ovo!",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from None
    except ValueError:
        # JSON解析失败属于上游返回无效内容；保留日志后转换成502。
        logger.exception("bailian embedding returned invalid json")
        raise BusinessException(
            message="知识库向量服务返回无效结果！Ovo!",
            status_code=status.HTTP_502_BAD_GATEWAY,
        ) from None

    # 记录融合向量用量（百炼 DashScope 口径）。
    await ai_usage_services.record_bailian_usage(
        "embedding",
        config.provider,
        config.model,
        response_data,
    )

    try:
        return _extract_embedding(response_data)
    except ValueError:
        logger.exception("bailian embedding response shape is invalid")
        raise BusinessException(
            message="知识库向量服务返回无效结果！Ovo!",
            status_code=status.HTTP_502_BAD_GATEWAY,
        ) from None

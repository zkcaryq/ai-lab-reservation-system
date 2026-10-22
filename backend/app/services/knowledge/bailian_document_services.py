"""通过百炼Responses API完成图片OCR和视觉描述。

document_parser_services在解析到扫描页或业务图片时调用本文件。OCR追求忠实抄录；
视觉理解负责解释空间关系和操作含义，两次调用的目标不同，结果会合并进同一个图片Chunk。
"""

import asyncio
import base64
import logging
import mimetypes
import re
from pathlib import Path

from fastapi import status

from app.core.errors import BusinessException
from app.core.settings import get_settings
from app.services.ai import ai_provider_services, ai_usage_services
from app.services.ai.providers import get_provider

settings = get_settings()
logger = logging.getLogger(__name__)

# 百炼文档解析有时会把临时OSS签名地址写进OCR结果。这些地址会过期，查询参数还
# 包含临时访问凭据，因此不能进入长期知识库，更不能原样回传前端。
_URL_PATTERN = re.compile(r"https?://[^\s<>'\"\])]+")


def sanitize_model_text(text: str) -> str:
    """移除模型文本中的临时签名URL，保留可检索的业务正文。"""

    def replace_url(match: re.Match[str]) -> str:
        """仅替换带临时凭据的 URL，普通公开链接保持原样。"""

        url = match.group(0)
        lowered = url.lower()
        sensitive_markers = (
            "ossaccesskeyid=",
            "signature=",
            "security-token=",
            "x-oss-security-token=",
            "docmind-api",
        )
        if any(marker in lowered for marker in sensitive_markers):
            return "[图片已由系统安全保存]"
        return url

    return _URL_PATTERN.sub(replace_url, text).replace("\x00", "").strip()


def _image_to_data_uri(path: Path) -> str:
    """把私有图片转成Responses input_image支持的Data URI。"""

    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type not in {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/bmp",
        "image/tiff",
    }:
        raise ValueError(f"不支持的图片格式：{path.suffix.lower()}")
    # 模型读取的是后端私有文件，不能生成公开URL，因此转换成Data URI随请求发送。
    raw = path.read_bytes()
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("OCR或视觉理解的图片不能超过20MiB")
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


async def get_image_data_uri(path: Path) -> str:
    """在线程中读取和Base64编码图片，避免同步磁盘I/O阻塞事件循环。"""

    return await asyncio.to_thread(_image_to_data_uri, path)


async def extract_image_text(image_path: Path) -> str:
    """使用OCR模型读取图片中的文字并尽量保留表格结构。

    走“ocr”能力配置（数据库优先、.env回退）。当前默认百炼专用OCR模型；
    extra_body的ocr_options是百炼专有参数，若以后切到其他供应商需按适配器差异处理。
    """

    config = await ai_provider_services.get_capability_config(None, "ocr")
    if config is None or not config.api_key:
        raise BusinessException(
            message="文档AI服务尚未配置，请联系管理员！Ovo!",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    image_url = await get_image_data_uri(image_path)
    # 通过供应商抽象层调用；OCR固定百炼，ocr_options经extra_body透传给百炼适配器。
    provider_impl = get_provider(config.provider)
    chat_result = await provider_impl.create_response(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.timeout_seconds,
        model=config.model,
        instructions="",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": image_url},
                    {
                        "type": "input_text",
                        "text": (
                            "请完整识别图片中的中文、英文、数字、型号和表格。"
                            "按照阅读顺序输出Markdown，不要总结，不要补充图片中没有的内容。"
                        ),
                    },
                ],
            }
        ],
        max_output_tokens=8_192,
        reasoning_effort=None,
        extra_body={"ocr_options": {"task": "document_parsing"}},
        dashscope_base_url=config.dashscope_base_url,
    )

    result = chat_result.text
    if not result:
        raise BusinessException(
            message="文档OCR没有返回有效文字！Ovo!",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    # 记录OCR用量。
    await ai_usage_services.record_usage(
        None,
        capability="ocr",
        provider=config.provider,
        model=config.model,
        result=chat_result,
    )
    return sanitize_model_text(result)


async def describe_image(image_path: Path, *, surrounding_text: str = "") -> str:
    """复用多模态模型解释图片语义、空间关系和操作含义。

    走“vision”能力配置（数据库优先、.env回退），与聊天能力解耦，管理员可单独
    为视觉理解指定供应商和模型。
    """

    config = await ai_provider_services.get_capability_config(None, "vision")
    if config is None or not config.api_key:
        raise BusinessException(
            message="文档AI服务尚未配置，请联系管理员！Ovo!",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    image_url = await get_image_data_uri(image_path)
    prompt = (
        "请描述这张智能实验室业务图片。重点识别实验室区域、设备、部件、连接关系、"
        "疏散方向、安全风险、正确或错误操作。只描述看得见的内容，不要猜测。"
    )
    if surrounding_text.strip():
        prompt += f"\n图片附近正文，仅用于辅助理解：\n{surrounding_text[:2000]}"

    # 通过供应商抽象层调用；请求格式由 provider 实现封装。
    provider_impl = get_provider(config.provider)
    chat_result = await provider_impl.create_response(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.timeout_seconds,
        model=config.model,
        instructions="",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": image_url},
                    {"type": "input_text", "text": prompt},
                ],
            }
        ],
        max_output_tokens=1_024,
        reasoning_effort=None,
        dashscope_base_url=config.dashscope_base_url,
    )

    result = chat_result.text
    if not result:
        raise BusinessException(
            message="图片视觉理解没有返回有效内容！Ovo!",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    # 记录视觉理解用量。
    await ai_usage_services.record_usage(
        None,
        capability="vision",
        provider=config.provider,
        model=config.model,
        result=chat_result,
    )
    return sanitize_model_text(result)


async def analyze_image(
    image_path: Path,
    *,
    surrounding_text: str = "",
) -> tuple[str | None, str | None]:
    """并发执行OCR和视觉理解；单项失败时保留另一项可用结果。

    文档中的图片既可能以文字为主，也可能以空间关系为主。OCR或视觉模型其中一个
    暂时失败，不应让整份包含大量正文的文档全部失败；只有两项都失败时才终止处理。
    """

    ocr_result, vision_result = await asyncio.gather(
        extract_image_text(image_path),
        describe_image(image_path, surrounding_text=surrounding_text),
        return_exceptions=True,
    )

    ocr_text: str | None = None
    description: str | None = None

    if isinstance(ocr_result, BaseException):
        logger.warning(
            "image OCR skipped after failure image=%s error_type=%s",
            image_path.name,
            type(ocr_result).__name__,
        )
    else:
        ocr_text = ocr_result

    if isinstance(vision_result, BaseException):
        logger.warning(
            "image vision skipped after failure image=%s error_type=%s",
            image_path.name,
            type(vision_result).__name__,
        )
    else:
        description = vision_result

    if ocr_text is None and description is None:
        # 对外只返回稳定提示；两项调用的具体异常已经由上面的模型函数或Worker日志记录。
        raise BusinessException(
            message="图片OCR和视觉理解均未得到有效结果！Ovo!",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    return ocr_text, description

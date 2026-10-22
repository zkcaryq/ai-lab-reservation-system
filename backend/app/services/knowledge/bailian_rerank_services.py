"""调用百炼文本排序模型，对向量召回候选进行二次排序。"""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.settings import get_settings
from app.services.ai import ai_provider_services, ai_usage_services
from app.services.ai.providers.bailian import resolve_dashscope_base

settings = get_settings()
logger = logging.getLogger(__name__)

# 端点：POST /api/v1/services/rerank/text-rerank/text-rerank
TEXT_RERANK_PATH = "/services/rerank/text-rerank/text-rerank"


@dataclass(frozen=True, slots=True)
class RerankResult:
    """一次重排结果；score只用于同一次请求内比较，不能跨请求比较。"""

    index: int
    relevance_score: float


def _extract_ranked_results(
    payload: dict[str, Any],
    *,
    document_count: int,
) -> list[RerankResult]:
    """验证百炼返回的候选索引与相关度分数，拒绝异常响应。"""

    try:
        results = payload["output"]["results"]
    except (KeyError, TypeError) as exc:
        raise ValueError("百炼Rerank响应缺少预期字段") from exc

    ranked_results: list[RerankResult] = []
    seen_indices: set[int] = set()
    for item in results:
        try:
            index = int(item["index"])
            relevance_score = float(item["relevance_score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("百炼Rerank响应包含无效索引或相关度分数") from exc
        if not 0 <= index < document_count or index in seen_indices:
            raise ValueError("百炼Rerank响应索引越界或重复")
        if not 0.0 <= relevance_score <= 1.0:
            raise ValueError("百炼Rerank响应相关度分数超出0到1")
        seen_indices.add(index)
        ranked_results.append(RerankResult(index=index, relevance_score=relevance_score))
    return ranked_results


async def rerank_documents_with_scores(
    *,
    query: str,
    documents: list[str],
    top_n: int,
) -> list[RerankResult] | None:
    """返回带分数的排序结果；无法调用模型时返回None，由调用方决定如何降级。"""

    if not documents:
        return []
    config = await ai_provider_services.get_capability_config(None, "rerank")
    if config is None or not config.api_key:
        logger.warning("rerank is configured but provider credentials are unavailable")
        return None

    url = resolve_dashscope_base(config.base_url, config.dashscope_base_url) + TEXT_RERANK_PATH
    request_body = {
        "model": config.model,
        "input": {
            "query": query,
            "documents": documents,
        },
        "parameters": {
            "top_n": min(top_n, len(documents)),
            "return_documents": False,
            "instruct": (
                "Given a laboratory knowledge query, retrieve passages that directly "
                "answer the query with concrete facts, rules, locations, times, or steps."
            ),
        },
    }

    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": "Bearer " + config.api_key,
                    "Content-Type": "application/json",
                },
                json=request_body,
            )
            response.raise_for_status()
            response_data = response.json()
            await ai_usage_services.record_bailian_usage(
                "rerank",
                config.provider,
                config.model,
                response_data,
            )
            return _extract_ranked_results(
                response_data,
                document_count=len(documents),
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("bailian rerank failed; falling back to fused retrieval", exc_info=True)
        return None


async def rerank_documents(
    *,
    query: str,
    documents: list[str],
    top_n: int,
) -> list[int]:
    """返回按相关性排序的原候选索引；失败时安全降级为原向量顺序。"""

    fallback = list(range(min(top_n, len(documents))))
    results = await rerank_documents_with_scores(
        query=query,
        documents=documents,
        top_n=top_n,
    )
    if results is None:
        return fallback
    return [result.index for result in results]

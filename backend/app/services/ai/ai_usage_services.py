"""AI 调用 token 用量记录与统计。

每次模型调用成功后落一条 AIUsageRecord，供管理员按能力（chat/vision/ocr/
embedding/rerank 等）统计消耗。不同供应商的 usage 字段口径略有差异，
这里做统一提取：input/output/total 三个必有，reasoning/cached 尽力取。
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_factory
from app.models.ai_provider_models import AIUsageRecord
from app.services.ai.providers.base import ChatResult


async def record_usage(
    db: AsyncSession | None,
    *,
    capability: str,
    provider: str,
    model: str,
    result: ChatResult,
    commit: bool = True,
) -> None:
    """把一次调用的统一用量落库；无用量信息时跳过。"""

    if result.input_tokens == 0 and result.output_tokens == 0 and result.total_tokens == 0:
        return

    fields = {
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "total_tokens": result.total_tokens,
        "reasoning_tokens": result.reasoning_tokens,
        "cached_tokens": result.cached_tokens,
    }

    if db is not None:
        db.add(AIUsageRecord(capability=capability, provider=provider, model=model, **fields))
        try:
            if commit:
                await db.commit()
            else:
                await db.flush()
        except Exception:
            await db.rollback()
            raise
    else:
        # 无外部Session（如worker里的视觉/OCR调用）时自开短Session。
        async with session_factory() as session:
            session.add(
                AIUsageRecord(capability=capability, provider=provider, model=model, **fields)
            )
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise


async def get_usage_summary(
    db: AsyncSession,
    *,
    days: int = 30,
) -> list[dict[str, object]]:
    """按能力聚合最近 N 天的用量，返回列表便于管理员页展示。"""

    cutoff = datetime.now(UTC) - timedelta(days=days)
    statement = (
        select(
            AIUsageRecord.capability,
            AIUsageRecord.provider,
            func.count().label("calls"),
            func.coalesce(func.sum(AIUsageRecord.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AIUsageRecord.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(AIUsageRecord.total_tokens), 0).label("total_tokens"),
        )
        .where(AIUsageRecord.created_at >= cutoff)
        .group_by(AIUsageRecord.capability, AIUsageRecord.provider)
        .order_by(func.sum(AIUsageRecord.total_tokens).desc())
    )
    rows = (await db.execute(statement)).all()
    return [
        {
            "capability": row.capability,
            "provider": row.provider,
            "calls": row.calls,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "total_tokens": row.total_tokens,
        }
        for row in rows
    ]


async def record_bailian_usage(
    capability: str,
    provider: str,
    model: str,
    response_data: dict,
) -> None:
    """记录百炼 DashScope 专有接口（embedding/rerank）的用量。

    百炼的 usage 字段口径与 OpenAI 兼容接口不同：rerank 返回 usage.total_tokens
    （部分模型含 prompt_tokens）；multimodal-embedding 返回 total_tokens /
    text_tokens / image_tokens。这里按百炼口径尽力提取并映射到统一表结构，
    output_tokens 对 embedding/rerank 恒为 0（无生成输出）。
    """

    usage = response_data.get("usage") or {}

    def _pick(*keys: str):
        """按不同供应商可能使用的字段名顺序提取首个 token 数值。"""

        for key in keys:
            value = usage.get(key) or response_data.get(key)
            if value is not None:
                return int(value)
        return None

    total = _pick("total_tokens")
    if total is None:
        return
    # 输入 token：rerank 用 prompt_tokens，embedding 用 text_tokens（不含图片 token）。
    input_tokens = _pick("prompt_tokens", "text_tokens") or 0

    async with session_factory() as session:
        session.add(
            AIUsageRecord(
                capability=capability,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=0,
                total_tokens=total,
            )
        )
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# 价格表：键 (provider, model)，值 (输入单价, 输出单价)，单位 元/百万 token。
# 数据来源（2026-10-20 查证，估算值，实际以官网/账单为准）：
# - MiniMax M3.1-Flash：官方国内定价 ¥1.00 输入 / ¥4.00 输出（缓存读 ¥0.10）；
#   MiniMax M3：¥2.10 输入 / ¥8.40 输出（标准服务、输入 ≤512K 档）。
#   注意：M Plan/Token Plan 订阅按额度计费，按量价仅作“等价价值”估算。
# - 百炼 qwen3.5-ocr：¥0.5 输入 / ¥2.0 输出（该模型没有独立的公开文档页，价格沿用上一轮查证）；
# - 百炼 qwen3-vl-embedding：文本 ¥0.7、**图片 ¥1.8**（输出不计费）。
#   数据库只记了 total_tokens，分不出文本和图片，这里统一按文本价 0.7 估 →
#   这一行是**下限**，真实花费最高可能是它的 2.57 倍。
# - 百炼 qwen3-rerank：¥0.5 输入（北京地域价，输出不计费；新加坡约 ¥0.749）；
# - 百炼 qwen3-vl-rerank：¥0.5（2026-09-01 降价后，文本与多模态同价）；
# - 百炼 tongyi-intent-detect-v3：¥0.4 输入 / ¥1.0 输出。
PRICING: dict[tuple[str, str], tuple[float, float]] = {
    ("minimax", "MiniMax-M3.1-Flash"): (1.0, 4.0),
    ("minimax", "MiniMax-M3"): (2.1, 8.4),
    ("bailian", "qwen3.5-ocr"): (0.5, 2.0),
    ("bailian", "qwen3-vl-embedding"): (0.7, 0.0),
    ("bailian", "qwen3-rerank"): (0.5, 0.0),
    ("bailian", "qwen3-vl-rerank"): (0.5, 0.0),
    ("bailian", "tongyi-intent-detect-v3"): (0.4, 1.0),
}


def _cost_of(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int = 0,
) -> float | None:
    """按价格表计算单次/聚合的估算花费；价格表无此模型时返回 None。

    rerank 与 embedding 这类"只进不出"的模型，百炼返回的 usage 里只有
    total_tokens（``record_bailian_usage`` 因此把 input/output 都记成 0），
    所以输入计费量要回退到 total_tokens，否则这两类永远算出 0 元。
    历史数据不动，只在这里补口径：有 input 用 input，没有就用 total - output。
    """

    price = PRICING.get((provider, model))
    if price is None:
        return None
    input_price, output_price = price
    billable_input = input_tokens or max(total_tokens - output_tokens, 0)
    return round(
        billable_input / 1_000_000 * input_price + output_tokens / 1_000_000 * output_price, 6
    )


async def get_cost_summary(
    db: AsyncSession,
    *,
    days: int = 30,
) -> dict[str, object]:
    """按能力+供应商+模型聚合最近 N 天用量并估算花费。"""

    cutoff = datetime.now(UTC) - timedelta(days=days)
    statement = (
        select(
            AIUsageRecord.capability,
            AIUsageRecord.provider,
            AIUsageRecord.model,
            func.count().label("calls"),
            func.coalesce(func.sum(AIUsageRecord.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AIUsageRecord.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(AIUsageRecord.total_tokens), 0).label("total_tokens"),
        )
        .where(AIUsageRecord.created_at >= cutoff)
        .group_by(AIUsageRecord.capability, AIUsageRecord.provider, AIUsageRecord.model)
        .order_by(func.sum(AIUsageRecord.total_tokens).desc())
    )
    rows = (await db.execute(statement)).all()

    items = []
    total_cost = 0.0
    priced_cost = 0.0
    for row in rows:
        cost = _cost_of(
            row.provider, row.model, row.input_tokens, row.output_tokens, row.total_tokens
        )
        if cost is not None:
            priced_cost += cost
            total_cost += cost
        items.append(
            {
                "capability": row.capability,
                "provider": row.provider,
                "model": row.model,
                "calls": row.calls,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "total_tokens": row.total_tokens,
                "cost": cost,  # None 表示价格表无此模型，未计入
            }
        )

    return {
        "days": days,
        "items": items,
        "total_cost": round(total_cost, 6),
        "priced_cost": round(priced_cost, 6),
        "currency": "CNY",
        "note": "估算值，单位元；价格表缺省的模型未计入，MiniMax订阅按等价价值估算，实际以官网/账单为准",
    }

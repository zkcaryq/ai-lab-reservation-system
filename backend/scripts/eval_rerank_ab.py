"""Rerank 对照评测：A 组（RRF融合后、无rerank）vs B 组（有rerank）。

为什么要这个脚本
----------------
生产代码 ``knowledge_retrieval_services.search_knowledge`` 里 rerank 是硬编码的，
而且 rerank 失败时会**静默回退**到向量顺序（见 ``bailian_rerank_services.rerank_documents``
的 ``fallback``）。所以"rerank 到底有没有用"不能只看线上回答，必须做对照。

本脚本的做法：
1. 只调用一次 embedding，得到同一批候选（向量 Top20 + 关键词补召回 Top20，按 chunk 去重）；
2. A 组直接取RRF融合候选前 5 条（等价于rerank失效时的真实回退行为）；
3. B 组把同一批候选交给真实的 ``rerank_documents`` 排序后取前 5 条。

因为两组候选完全相同，指标差异只能归因于排序方式。

指标
----
- Hit@K：期望文档出现在前 K 条里即算命中（Recall@K 的单条口径）；
- MRR@5：第一条命中的排名的倒数（越接近 1 越好，没命中记 0）；
- 去重文档数：前 5 条里出现了几份不同文档（衡量"同一文档刷屏"）。

用法
----
    python -m scripts.eval_rerank_ab
    python -m scripts.eval_rerank_ab --cases evals/rag_cases_ab.json --limit 5

注意：每条用例会产生 1 次 embedding 和 1 次 rerank 调用。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_loop import loop_factory
from app.core.settings import get_settings
from app.db.session import engine, session_factory
from app.models.knowledge_models import KnowledgeChunk
from app.services.knowledge.bailian_embedding_services import create_fused_embedding
from app.services.knowledge.bailian_rerank_services import rerank_documents
from app.services.knowledge.knowledge_retrieval_services import (
    build_candidate_rows,
    build_rerank_document,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = PROJECT_ROOT / "evals" / "rag_cases_ab.json"

settings = get_settings()

CandidateRow = tuple[KnowledgeChunk, str, float]


async def build_candidates(
    session: AsyncSession,
    *,
    query: str,
    query_embedding: list[float],
    candidate_limit: int,
) -> list[CandidateRow]:
    """复用生产候选构建逻辑，保证A/B评测不会与线上实现漂移。"""

    return await build_candidate_rows(
        session,
        query=query,
        query_embedding=query_embedding,
        candidate_limit=candidate_limit,
    )


def first_hit_rank(names: list[str], expected: list[str], k: int) -> int | None:
    """返回期望文档第一次出现在前 k 条中的排名（从 1 开始）；没命中返回 None。"""

    for rank, name in enumerate(names[:k], start=1):
        if any(marker in name for marker in expected):
            return rank
    return None


def distinct_doc_count(names: list[str], k: int) -> int:
    return len(set(names[:k]))


def summarize(records: list[dict[str, Any]], arm: str, k: int) -> dict[str, float]:
    """把一个分组的逐条结果汇总成指标。"""

    ranks = [record[f"{arm}_rank"] for record in records]
    hits = [rank for rank in ranks if rank is not None]
    reciprocal = [1.0 / rank if rank else 0.0 for rank in ranks]
    return {
        "hit@1": sum(1 for rank in ranks if rank == 1) / len(records),
        "hit@3": sum(1 for rank in ranks if rank is not None and rank <= 3) / len(records),
        f"hit@{k}": len(hits) / len(records),
        "mrr@5": statistics.fmean(reciprocal),
        "distinct_docs": statistics.fmean([record[f"{arm}_distinct"] for record in records]),
    }


def verdict_of(rank_a: int | None, rank_b: int | None) -> str:
    if rank_a is None and rank_b is None:
        return "= 都未中"
    if rank_a is None:
        return "↑ 提升"
    if rank_b is None:
        return "↓ 变差"
    if rank_b < rank_a:
        return "↑ 提前"
    if rank_b > rank_a:
        return "↓ 推后"
    return "= 相同"


def print_details(records: list[dict[str, Any]], k: int) -> None:
    """打印逐条对比。"""

    print("\n" + "=" * 96)
    print(f"逐条对比（rank = 期望文档首次出现的排名，'-' 表示前 {k} 条未命中）")
    print("=" * 96)
    header = f"{'#':<3} {'问题':<34} {'A无rerank':<9} {'B有rerank':<9} {'结论':<8} B组命中文档"
    print(header)
    print("-" * 96)

    for index, record in enumerate(records, start=1):
        rank_a = record["no_rerank_rank"]
        rank_b = record["rerank_rank"]
        text_a = "-" if rank_a is None else f"第{rank_a}"
        text_b = "-" if rank_b is None else f"第{rank_b}"
        verdict = verdict_of(rank_a, rank_b)
        top_name = record["rerank_names"][0] if record["rerank_names"] else "-"
        print(
            f"{index:<3} {record['question'][:32]:<34} "
            f"{text_a:<9} {text_b:<9} {verdict:<8} {top_name[:28]}"
        )


def print_summary(records: list[dict[str, Any]], k: int) -> None:
    """打印汇总对比表。"""

    print("\n" + "=" * 96)
    print(f"汇总（共 {len(records)} 条用例）")
    print("=" * 96)
    summary_a = summarize(records, "no_rerank", k)
    summary_b = summarize(records, "rerank", k)

    print(f"{'指标':<16}{'A 无 rerank':>14}{'B 有 rerank':>14}{'差值':>10}")
    print("-" * 60)
    for key in ("hit@1", "hit@3", f"hit@{k}", "mrr@5", "distinct_docs"):
        value_a = summary_a[key]
        value_b = summary_b[key]
        delta = value_b - value_a
        print(f"{key:<16}{value_a:>14.3f}{value_b:>14.3f}{delta:>+10.3f}")

    latencies = [record["rerank_seconds"] for record in records]
    print(
        f"\nrerank 单次调用平均耗时：{statistics.fmean(latencies):.3f}s"
        f"（最长 {max(latencies):.3f}s）"
    )


async def evaluate(cases: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """逐条跑 A/B 两组，返回逐条结果记录。"""

    candidate_limit = max(limit, settings.RAG_CANDIDATE_LIMIT)
    print(
        f"用例 {len(cases)} 条｜TopK={limit}｜候选上限={candidate_limit}"
        f"｜embedding={settings.BAILIAN_EMBEDDING_DIMENSION}｜rerank=已启用"
    )

    records: list[dict[str, Any]] = []
    async with session_factory() as session:
        for index, case in enumerate(cases, start=1):
            question = case["question"]
            expected = case["expected"]
            print(f"  [{index:2d}/{len(cases)}] {question}")

            query_embedding = await create_fused_embedding(text=question)
            candidates = await build_candidates(
                session,
                query=question,
                query_embedding=query_embedding,
                candidate_limit=candidate_limit,
            )
            if not candidates:
                print("        跳过：没有候选")
                continue

            # A组：直接取RRF融合候选前limit条，等价于rerank失效时的回退行为。
            no_rerank_names = [row[1] for row in candidates[:limit]]

            # B 组：对同一批候选做真实的 rerank 排序。
            started = time.perf_counter()
            ranked_indices = await rerank_documents(
                query=question,
                # 与生产检索完全一致：排序模型同时看到来源文件名、章节和正文。
                documents=[build_rerank_document(row[0], file_name=row[1]) for row in candidates],
                top_n=limit,
            )
            elapsed = time.perf_counter() - started
            rerank_names = [candidates[i][1] for i in ranked_indices]

            records.append(
                {
                    "question": question,
                    "no_rerank_names": no_rerank_names,
                    "rerank_names": rerank_names,
                    "no_rerank_rank": first_hit_rank(no_rerank_names, expected, limit),
                    "rerank_rank": first_hit_rank(rerank_names, expected, limit),
                    "no_rerank_distinct": distinct_doc_count(no_rerank_names, limit),
                    "rerank_distinct": distinct_doc_count(rerank_names, limit),
                    "rerank_seconds": elapsed,
                }
            )

            # rerank 原样返回 fallback 顺序时，说明调用失败被兜底了，需要提示。
            if ranked_indices == list(range(min(limit, len(candidates)))):
                print("        ⚠ rerank 可能已失败并回退（返回顺序与候选顺序一致）")

    return records


async def main() -> None:
    parser = argparse.ArgumentParser(description="Rerank A/B 对照评测")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))

    try:
        records = await evaluate(cases, args.limit)
    finally:
        await engine.dispose()

    if not records:
        print("没有有效结果")
        return

    print_details(records, args.limit)
    print_summary(records, args.limit)


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(main())

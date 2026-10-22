"""运行RAG检索评测集，不调用最终聊天模型。

用法：
    uv run python -m scripts.evaluate_rag
    uv run python -m scripts.evaluate_rag --cases evals/rag_cases_hard.json

每个问题会调用一次融合向量接口，并在已入库Chunk中执行与正式聊天相同的检索流程。
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.core.event_loop import loop_factory
from app.db.session import engine, session_factory
from app.services.knowledge.knowledge_retrieval_services import search_knowledge

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = PROJECT_ROOT / "evals" / "rag_cases.json"


def _case_expectations(case: dict) -> tuple[list[str], list[str], list[str]]:
    """兼容旧用例，并支持困难用例的全部命中和禁止命中规则。"""

    expected_any = case.get("expected_any") or case.get("expected") or []
    legacy = case.get("expected_source_contains")
    if legacy:
        expected_any = [legacy] if isinstance(legacy, str) else list(legacy)
    if isinstance(expected_any, str):
        expected_any = [expected_any]
    return (
        list(expected_any),
        list(case.get("expected_all") or []),
        list(case.get("forbidden") or []),
    )


def _contains_marker(names: list[str], marker: str) -> bool:
    return any(marker in name for name in names)


async def main() -> None:
    parser = argparse.ArgumentParser(description="运行RAG来源召回评测")
    parser.add_argument("--cases", default=str(CASES_PATH))
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    cases_path = Path(args.cases)
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    passed = 0
    required_hits = 0
    required_total = 0

    try:
        async with session_factory() as session:
            for index, case in enumerate(cases, start=1):
                results = await search_knowledge(
                    session,
                    query=case["question"],
                    focus_question=case["question"],
                    limit=args.limit,
                )
                source_names = [item.file_name for item in results]
                expected_any, expected_all, forbidden = _case_expectations(case)
                any_ok = not expected_any or any(
                    _contains_marker(source_names, marker) for marker in expected_any
                )
                all_ok = all(_contains_marker(source_names, marker) for marker in expected_all)
                forbidden_ok = not any(
                    _contains_marker(source_names, marker) for marker in forbidden
                )
                hit = any_ok and all_ok and forbidden_ok
                passed += int(hit)
                required = [*expected_all]
                if expected_any:
                    required.append("任一：" + " / ".join(expected_any))
                required_total += len(required)
                required_hits += sum(
                    _contains_marker(source_names, marker) for marker in expected_all
                ) + int(
                    bool(expected_any)
                    and any(_contains_marker(source_names, marker) for marker in expected_any)
                )
                print(f"[{index}] {'PASS' if hit else 'FAIL'} {case['question']}")
                print(f"    expected_any: {expected_any}")
                print(f"    expected_all: {expected_all}")
                print(f"    forbidden: {forbidden}")
                print(f"    sources: {source_names}")
    finally:
        await engine.dispose()

    print(f"\nCasePass@{args.limit}: {passed}/{len(cases)} = {passed / max(len(cases), 1):.1%}")
    print(
        f"EvidenceRecall@{args.limit}: {required_hits}/{required_total} = "
        f"{required_hits / max(required_total, 1):.1%}"
    )


if __name__ == "__main__":
    # psycopg 的异步连接在 Windows 下不能使用默认 ProactorEventLoop。
    # 与应用入口、知识库 Worker 保持一致，显式使用项目提供的 Selector loop。
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(main())

"""独立运行知识文档Worker，供生产环境与Web进程分离部署。

PowerShell：uv run python -m scripts.run_knowledge_worker
使用该命令时应把Web进程的KNOWLEDGE_WORKER_ENABLED设为false，避免重复Worker。
"""

import asyncio

from app.core.event_loop import loop_factory
from app.db.session import engine
from app.services.knowledge.knowledge_storage_services import ensure_knowledge_directories
from app.services.knowledge.knowledge_worker_services import run_knowledge_worker


async def main() -> None:
    ensure_knowledge_directories()
    try:
        await run_knowledge_worker()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(main())

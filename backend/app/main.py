"""FastAPI 应用装配入口。"""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes.health_router import router as health_router
from app.core.body_limit import BodySizeLimitMiddleware
from app.core.errors import (
    BusinessException,
    UnexpectedErrorMiddleware,
    business_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.core.request_id import RequestIdMiddleware
from app.core.settings import get_settings
from app.db.session import engine
from app.services.knowledge import knowledge_worker_services
from app.services.knowledge.knowledge_storage_services import ensure_knowledge_directories
from app.services.reservation import reservation_services

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期：准备运行目录、启动后台任务，并在关闭时安全释放资源。

    启动阶段只准备运行所需目录和后台任务，
    不创建数据库、Schema、表，也不自动执行 Alembic 迁移。
    """

    # -------------------------
    # 启动阶段
    # -------------------------

    # 创建公开上传目录，例如用户头像。
    # parents=True：缺失的父目录也会一起创建。
    # exist_ok=True：目录已经存在时不会报错。
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # 创建 RAG 知识库私有存储目录。
    # 例如原始文档、解析结果、提取图片等。
    # 必须在 Knowledge Worker 启动之前完成。
    ensure_knowledge_directories()

    # 启动知识库异步摄取 Worker。
    # Worker 会持续处理 queued 状态的知识文档。
    knowledge_task: asyncio.Task[None] | None = None
    if settings.KNOWLEDGE_WORKER_ENABLED:
        knowledge_task = asyncio.create_task(
            knowledge_worker_services.run_knowledge_worker(),
            name="knowledge-ingestion-worker",
        )

    # 启动预约自动审核后台任务。
    review_task = asyncio.create_task(
        reservation_services.run_pending_reservation_scan(),
        name="pending-reservation-scan",
    )

    try:
        # yield 之前属于 FastAPI 启动阶段。
        # 执行到这里之后，应用才正式开始接受 HTTP 请求。
        yield

    finally:
        # -------------------------
        # 关闭阶段
        # -------------------------

        # 必须先停止仍可能访问数据库的后台任务，
        # 然后才能释放 SQLAlchemy Engine。
        if knowledge_task is not None:
            knowledge_task.cancel()
        review_task.cancel()

        try:
            async with asyncio.timeout(settings.SHUTDOWN_TIMEOUT):
                with suppress(asyncio.CancelledError):
                    tasks = [review_task]
                    if knowledge_task is not None:
                        tasks.append(knowledge_task)
                    await asyncio.gather(*tasks)
        except TimeoutError:
            logger.warning("background tasks timed out during shutdown")
        except Exception:
            logger.exception("background tasks failed during shutdown")

        # 所有后台任务停止后，再释放数据库连接池。
        try:
            async with asyncio.timeout(settings.SHUTDOWN_TIMEOUT):
                await engine.dispose()
        except TimeoutError:
            logger.warning("engine dispose timed out during shutdown")
        except Exception:
            logger.exception("engine dispose failed during shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    debug=False,
    lifespan=lifespan,
    docs_url=None if settings.APP_ENV == "production" else "/docs",
    redoc_url=None,
    openapi_url=None if settings.APP_ENV == "production" else "/openapi.json",
)

# 把URL前缀/uploads映射到本地上传目录，使公开头像可以通过URL直接读取。
app.mount(
    # 浏览器请求路径前缀，例如GET /uploads/abc.png。
    "/uploads",
    # StaticFiles负责根据URL末尾文件名读取目录中的对应文件并返回。
    StaticFiles(
        # directory接受Path；实际默认值为backend/uploads。
        directory=settings.UPLOAD_DIR,
        # 应用装配时目录可能尚未由lifespan创建，因此这里关闭立即检查。
        # 正式接收请求前lifespan一定会创建目录。
        check_dir=False,
    ),
    # name是Starlette内部路由名称，可用于反向生成URL。
    name="uploads",
)

# Starlette 后添加的中间件位于外层。下面的注册顺序不能随意交换。
# 实际请求顺序为：RequestId -> CORS -> UnexpectedError -> BodySizeLimit -> Router。
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.MAX_REQUEST_BODY_BYTES)
app.add_middleware(UnexpectedErrorMiddleware)

# CORS只决定浏览器是否允许前端JavaScript读取响应，不负责登录和权限验证。
# Authorization能否跨域发送由allow_headers控制；allow_credentials主要用于Cookie等凭据。
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.CORS_ORIGINS),
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "X-Request-ID"],
    # 让浏览器端JavaScript可以读取后端写入响应头的请求追踪编号。
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestIdMiddleware)

# 预期内业务失败由BusinessException处理器统一转换，Router不再手写错误字典。
app.add_exception_handler(BusinessException, business_exception_handler)

# 注册Starlette的HTTPException基类，可同时覆盖FastAPI主动异常以及框架的404/405。
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

# 请求体、Query和Path参数未通过Pydantic校验时，统一返回安全的字段错误信息。
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# 注意：这里故意不注册Exception处理器。
# 未知异常必须继续向外传播，由UnexpectedErrorMiddleware记录完整堆栈和error_id。

# 健康检查保持根路径；所有业务Router统一挂到带/api前缀的api_router。
app.include_router(health_router)
app.include_router(api_router)

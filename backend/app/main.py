"""FastAPI 应用装配入口。"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes.health import router as health_router
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

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用关闭时限时释放连接池；启动阶段不修改数据库结构。"""

    try:
        yield
    finally:
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

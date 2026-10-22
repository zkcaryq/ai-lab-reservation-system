"""统一错误处理：格式化预期错误，并安全记录未知服务器异常。

错误会沿两条不同路径处理：

1. 预期错误（业务失败、HTTP错误、参数校验失败）由FastAPI异常处理器
   转换为统一的 ``code/message/data``，通常不记录完整堆栈；
2. 未知错误（程序Bug、未处理的数据库异常等）穿过FastAPI处理层后，
   由 ``UnexpectedErrorMiddleware`` 记录完整堆栈并返回追踪编号。

这种区分很重要：账号密码错误不是服务器Bug，不需要制造ERROR堆栈；
数据库ProgrammingError却必须保留traceback，否则只有“500”而无法定位原因。
"""

# logging负责把未知异常写入终端和本次启动对应的日志文件。
import logging

# uuid用于给每一次未知异常生成唯一error_id。
import uuid

# Request是异常处理器固定会接收的当前HTTP请求对象。
from fastapi import Request

# RequestValidationError表示请求体、Query或Path参数没有通过Pydantic校验。
from fastapi.exceptions import RequestValidationError

# JSONResponse允许我们同时指定真实HTTP状态码和统一JSON内容。
from fastapi.responses import JSONResponse

# 使用Starlette基类可以同时覆盖FastAPI主动抛出的HTTPException和框架产生的404/405。
from starlette.exceptions import HTTPException as StarletteHTTPException

# 下面是纯ASGI中间件需要的类型：应用、消息、接收函数、请求信息和发送函数。
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# current_request_id()读取最外层RequestIdMiddleware为当前请求保存的编号。
from app.core.request_id import current_request_id

# 所有失败响应都通过ApiResponse生成相同的code/message/data外形。
from app.schemas.apiresponse import ApiResponse

# 使用当前模块名创建logger，日志中会显示logger=app.core.errors。
logger = logging.getLogger(__name__)


class UnexpectedErrorMiddleware:
    """捕获未被明确异常处理器消费的未知服务器异常。"""

    def __init__(self, app: ASGIApp) -> None:
        """保存下一层 ASGI 应用。"""

        # app代表中间件内侧的下一个ASGI应用。
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理一次ASGI调用；只对HTTP请求执行错误包装。"""

        # lifespan和WebSocket不是普通HTTP响应，直接交给内层应用。
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 记录响应头是否已经发送。响应一旦开始，就不能再改成一个新的500响应。
        response_started = False

        async def tracking_send(message: Message) -> None:
            """代理send，并观察内层应用是否已经发出HTTP响应头。"""

            # nonlocal表示这里修改的是外层__call__中的同名变量。
            nonlocal response_started

            # http.response.start包含状态码与响应头，出现它就表示响应已经开始。
            if message["type"] == "http.response.start":
                response_started = True

            # 观察完成后仍要把原消息发送出去，不能截断正常响应。
            await send(message)

        try:
            # 正常情况下调用内层应用；发送响应时改用上面的tracking_send。
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            # 能来到这里，说明异常没有被业务、HTTP或422处理器消费，属于未知异常。
            # 每次异常都生成独立error_id，方便用户拿着编号查询具体日志。
            error_id = uuid.uuid4().hex

            # logger.error把检索字段写入日志；exc_info=exc会追加完整Python traceback。
            logger.error(
                "unhandled_error",
                extra={
                    "error_id": error_id,
                    "request_method": scope.get("method", "-"),
                    "request_path": scope.get("path", "-"),
                },
                exc_info=exc,
            )

            # 如果流式响应等场景已经发出了响应头，就不能再发送第二套500响应头。
            # 继续抛出异常，让服务器正确终止当前响应，而不是伪造一个结构完整的500。
            if response_started:
                raise

            # 对客户端只返回安全提示和追踪编号，不返回异常文本、SQL或traceback。
            response_body = ApiResponse.error(
                code=500,
                message="服务器内部错误",
                data={
                    "error_id": error_id,
                    "request_id": current_request_id(),
                },
            )

            # ApiResponse是Pydantic对象；model_dump(mode="json")把它转成可JSON编码的字典。
            response = JSONResponse(
                status_code=500,
                content=response_body.model_dump(mode="json"),
            )

            # Starlette响应对象本身也是ASGI应用，需要传入scope/receive/send才能真正发送。
            await response(scope, receive, send)


class BusinessException(Exception):
    """表示预期内、可以安全告诉客户端的业务失败。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        """保存可公开提示与对应 HTTP 状态码。"""

        # message是可以返回客户端的业务提示，不能包含SQL、密码或内部堆栈。
        self.message = message

        # status_code决定真实HTTP状态码，本章让JSON code与它保持一致。
        self.status_code = status_code

        # 初始化Exception基类，使调试器和str(exc)仍然可以取得异常消息。
        super().__init__(message)


async def business_exception_handler(
    _request: Request,
    exc: BusinessException,
) -> JSONResponse:
    """把预期内业务异常转换成统一JSON响应。"""

    # 参数名前的下划线表示FastAPI会传入Request，但本函数当前不需要使用它。
    # 用异常携带的状态码和安全消息创建统一JSON内容。
    response_body = ApiResponse.error(
        code=exc.status_code,
        message=exc.message,
    )

    # 真实HTTP状态码与JSON code使用同一个值，避免HTTP 200包装业务失败。
    return JSONResponse(
        status_code=exc.status_code,
        content=response_body.model_dump(mode="json"),
    )


async def http_exception_handler(
    _request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """统一主动HTTP错误以及框架生成的404、405响应。"""

    # 当前项目使用的detail都是字符串；str()同时兼容Starlette默认的404/405消息。
    response_body = ApiResponse.error(
        code=exc.status_code,
        message=str(exc.detail),
    )

    # 必须保留exc.headers，例如Bearer鉴权失败需要WWW-Authenticate: Bearer。
    return JSONResponse(
        status_code=exc.status_code,
        content=response_body.model_dump(mode="json"),
        headers=exc.headers,
    )


async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """统一请求JSON、Query和Path参数没有通过Pydantic校验时的响应。"""

    # exc.errors()还可能包含用户原始input或内部ctx。
    # 这里只保留前端定位字段所需的loc/type/msg，避免把密码等输入回显给客户端。
    issues = [
        {
            "loc": list(error["loc"]),
            "type": error["type"],
            "msg": error["msg"],
        }
        for error in exc.errors()
    ]

    # 422表示请求格式可解析，但字段内容没有通过Schema校验。
    response_body = ApiResponse.error(
        code=422,
        message="请求参数校验错误",
        data={"errors": issues},
    )

    # 返回真实HTTP 422，同时保持统一JSON外形。
    return JSONResponse(
        status_code=422,
        content=response_body.model_dump(mode="json"),
    )

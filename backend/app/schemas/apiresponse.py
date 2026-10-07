"""业务API共用的最外层响应结构。

调用位置：
- Router使用 ``ApiResponse.success()`` 创建成功响应；
- 异常处理器和请求体限制中间件使用 ``ApiResponse.error()`` 创建失败响应。

本类只描述JSON内容，不决定真正的HTTP状态码。HTTP状态码仍由Router装饰器
或 ``JSONResponse(status_code=...)`` 设置，两处数值必须保持一致。
"""

# Any表示不同接口的data可以放不同类型的数据。
from typing import Any

# BaseModel让ApiResponse获得类型校验和JSON序列化能力。
from pydantic import BaseModel


class ApiResponse(BaseModel):
    """统一返回 ``code``、``message`` 和 ``data`` 三个字段。"""

    # JSON中的结果码；当前阶段约定它与真实HTTP状态码相同。
    code: int

    # 给前端和用户阅读的结果说明，不能放SQL、堆栈或密码等内部信息。
    message: str

    # 具体业务数据。没有数据时使用None，序列化成JSON后就是null。
    data: Any = None

    @classmethod
    def success(
        cls,
        *,
        code: int = 200,
        message: str = "请求成功",
        data: Any = None,
    ) -> "ApiResponse":
        """创建成功响应对象；默认用于HTTP 200场景。"""

        # cls代表当前类ApiResponse；使用cls而不是写死类名，便于以后继承。
        # 这里只创建JSON数据，Router仍需负责设置真实HTTP状态码。
        return cls(code=code, message=message, data=data)

    @classmethod
    def error(
        cls,
        *,
        code: int,
        message: str,
        data: Any = None,
    ) -> "ApiResponse":
        """创建失败响应对象；真实HTTP状态码由异常处理器或中间件设置。"""

        # 错误时通常没有data；未知500会在data里放request_id和error_id。
        return cls(code=code, message=message, data=data)

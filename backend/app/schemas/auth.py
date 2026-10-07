from pydantic import BaseModel

# LoginResponse会把对外用户信息嵌套在登录成功的data中。
from app.schemas.user import UserResponse


class LoginRequest(BaseModel):
    """定义登录请求体的结构。

    ``app/api/routes/auth.py`` 中的 ``login(data: LoginRequest, ...)`` 会使用
    这个Schema。客户端提交的JSON会由FastAPI和Pydantic解析为本类的对象，
    Router随后可以通过 ``data.username`` 和 ``data.password`` 读取字段。
    """

    # 对应请求JSON中的username字段。
    username: str

    # 对应请求JSON中的password字段；本章不提前增加额外校验。
    password: str


class LoginResponse(BaseModel):
    """定义登录成功后 ``ApiResponse.data`` 内部的结构。"""

    # 登录Router调用create_access_token(user.id)生成的JWT字符串。
    token: str

    # UserResponse只包含允许公开的用户字段，不包含User.password。
    user: UserResponse

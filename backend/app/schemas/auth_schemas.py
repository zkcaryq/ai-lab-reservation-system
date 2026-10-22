"""认证模块使用的请求与响应Schema。

调用关系：
- Router用LoginRequest解析登录JSON；
- Router用RegisterRequest解析注册JSON；
- Router用LoginResponse约束登录成功时ApiResponse.data的内部结构。

Schema只负责描述和校验数据结构，不查询数据库，也不处理HTTP响应。
"""

# BaseModel是所有Pydantic Schema的基类，让类获得请求解析、类型校验和序列化能力。
from pydantic import BaseModel

# LoginResponse会把对外用户信息嵌套在登录成功的data中。
from app.schemas.user_schemas import UserResponse


class LoginRequest(BaseModel):
    """定义登录请求体的结构。

    ``app/api/routes/auth_router.py`` 中的 ``login(data: LoginRequest, ...)`` 会使用
    这个Schema。客户端提交的JSON会由FastAPI和Pydantic解析为本类的对象，
    Router随后可以通过 ``data.username`` 和 ``data.password`` 读取字段。
    """

    # 对应请求JSON中的username字段。
    username: str

    # 对应请求JSON中的password字段；本章不提前增加额外校验。
    password: str


class RegisterRequest(BaseModel):
    """定义用户注册接口接收的JSON结构。

    ``app/api/routes/auth_router.py``中的``register()``使用本Schema。
    FastAPI会先把客户端JSON转换为RegisterRequest，再执行Router函数。
    """

    # 注册账号，由Service用于查询是否已经存在并写入User.username。
    username: str

    # 用户输入的明文密码，只能短暂用于生成Argon2id哈希，不能直接存入数据库。
    password: str

    # 名称可以不传；缺省时Service会使用username作为显示名称。
    name: str | None = None


class LoginResponse(BaseModel):
    """定义登录成功后 ``ApiResponse.data`` 内部的结构。"""

    # 登录Router调用create_access_token(user.id)生成的JWT字符串。
    token: str

    # UserResponse只包含允许公开的用户字段，不包含User.password。
    user: UserResponse

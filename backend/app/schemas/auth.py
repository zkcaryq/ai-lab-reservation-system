from pydantic import BaseModel


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

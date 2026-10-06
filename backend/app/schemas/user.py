from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    """定义登录成功后允许返回给客户端的用户字段。

    Router通过 ``UserResponse.model_validate(user)`` 把SQLAlchemy的User对象
    转换成本Schema。这里没有声明password，所以响应中不会包含密码字段。
    """

    # 默认情况下，Pydantic更擅长读取字典；from_attributes=True允许它读取
    # SQLAlchemy对象的user.id、user.username等同名属性。
    model_config = ConfigDict(from_attributes=True)

    # 以下字段名需要与User ORM模型中的属性名保持一致。
    id: int
    username: str
    name: str
    role: str
    phone: str | None = None
    email: str | None = None
    status: int

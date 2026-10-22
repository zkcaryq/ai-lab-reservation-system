"""用户资料、管理员用户管理与密码修改的 Pydantic 模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UserResponse(BaseModel):
    """定义允许返回给客户端的公开用户字段。

    登录、当前用户资料和管理员用户列表都会复用本Schema。Router通过
    ``UserResponse.model_validate(user)``把SQLAlchemy User转换成本对象。
    本类没有声明password，因此数据库中的Argon2id哈希不会进入API响应。
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
    avatar: str | None = None
    status: int

    # ORM使用带时区DateTime；Pydantic序列化后会返回ISO 8601字符串。
    # 例如UTC时间显示为2026-10-05T23:33:41Z，前端负责转换为北京时间展示。
    created_at: datetime


class UserUpdateRequest(BaseModel):
    """定义当前用户资料修改接口允许接收的字段。

    这是请求Schema，所以使用Request命名。所有字段都允许不提交，符合PATCH
    “只修改本次提供字段”的语义。username、password、role和status没有出现在
    本类中，因此资料修改接口不会把它们交给Service更新。
    """

    # 显示名称；没有提交时为None，Service不会修改原值。
    name: str | None = None

    # 手机号、邮箱和头像地址都属于可选资料字段。
    phone: str | None = None
    email: str | None = None
    avatar: str | None = None


class PasswordUpdateRequest(BaseModel):
    """修改当前用户密码时接收的明文旧密码和新密码。"""

    # 旧密码只用于和数据库中的Argon2id哈希验证，不会保存到数据库。
    old_password: str

    # 新密码会在Service中通过hash_password()转换成Argon2id哈希后再保存。
    new_password: str


class UserPageResponse(BaseModel):
    """管理员分页查询用户时，放在ApiResponse.data中的分页数据。"""

    # list只保存当前页记录；每项受UserResponse约束，因此不会包含password。
    list: list[UserResponse]

    # total是符合搜索条件的总记录数，不是当前页list的长度。
    # 前端分页器通过total和page_size计算总页数。
    total: int


class AdminCreateUserRequest(BaseModel):
    """管理员创建用户时允许提交的字段。"""

    # username最终写入User.username；max_length与数据库String(50)保持一致。
    # min_length会在进入Router前拒绝空字符串，失败时由全局处理器返回HTTP 422。
    username: str = Field(min_length=1, max_length=50)

    # 管理员不传password时使用本章约定的初始密码123456。
    # 如果主动传入密码，长度必须在6～128之间；空字符串不会触发默认值，而会返回422。
    # Service会使用Argon2id哈希，数据库不会保存这段明文。
    password: str = Field(default="123456", min_length=6, max_length=128)

    # name可以省略；Service创建ORM对象时会回退为username，满足数据库NOT NULL约束。
    name: str | None = Field(default=None, max_length=50)

    # 以下三个字段对应User ORM中的可空列；Field上限与数据库列长度保持一致。
    email: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=50)
    avatar: str | None = Field(default=None, max_length=500)

    # Literal在进入Router前拦截其他任意角色字符串。
    role: Literal["student", "admin"] = "student"

    # 当前系统只约定0=禁用、1=正常。
    status: Literal[0, 1] = 1


class AdminUpdateUserRequest(BaseModel):
    """管理员通过PATCH部分修改指定用户时允许提交的字段。"""

    # 全部字段可选，符合PATCH“只改本次提交字段”的语义。
    # username和password没有出现在本类中，因此本接口不会修改账号和认证凭据。
    name: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=50)
    avatar: str | None = Field(default=None, max_length=500)

    # 管理员更新接口可以调整角色和状态，但值仍被Literal限制在系统约定范围内。
    role: Literal["student", "admin"] | None = None
    status: Literal[0, 1] | None = None

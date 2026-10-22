"""实验室接口的 Pydantic 请求、响应与分页模型。"""

from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LabResponse(BaseModel):
    """定义允许返回给客户端的实验室字段。

    Router通过``LabResponse.model_validate(lab)``把SQLAlchemy Lab转换为
    本对象，只输出这里明确声明的字段。
    """

    # 默认情况下，Pydantic更擅长读取字典；from_attributes=True允许它读取
    # SQLAlchemy对象的lab.id、lab.name等同名属性。
    model_config = ConfigDict(from_attributes=True)

    # 以下字段名需要与Lab ORM模型中的属性名保持一致。
    id: int
    name: str
    location: str | None = None
    capacity: int
    open_time: time | None = None
    close_time: time | None = None
    description: str | None = None
    img: str | None = None
    status: int
    created_at: datetime
    updated_at: datetime


class LabCreateRequest(BaseModel):
    """管理员创建实验室时允许提交的字段。"""

    name: str = Field(min_length=1, max_length=50)
    location: str | None = Field(default=None, max_length=100)
    capacity: int = Field(default=0, ge=0, le=500)
    open_time: time | None = None
    close_time: time | None = None
    description: str | None = Field(default=None, max_length=500)
    img: str | None = Field(default=None, max_length=500)
    status: Literal[0, 1] = 1


class LabUpdateRequest(BaseModel):
    """管理员通过PATCH部分修改实验室时允许提交的字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    location: str | None = Field(default=None, max_length=100)
    capacity: int | None = Field(default=None, ge=0, le=500)
    open_time: time | None = None
    close_time: time | None = None
    description: str | None = Field(default=None, max_length=500)
    img: str | None = Field(default=None, max_length=500)
    status: Literal[0, 1] | None = None


class LabPageResponse(BaseModel):
    """实验室分页接口的data结构。"""

    list: list[LabResponse]
    total: int

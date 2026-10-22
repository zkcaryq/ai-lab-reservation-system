"""设备接口的 Pydantic 请求、响应与分页模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EquipmentResponse(BaseModel):
    """返回给前端的设备公开字段。"""

    # 允许model_validate()从SQLAlchemy Equipment对象读取同名属性。
    model_config = ConfigDict(from_attributes=True)

    id: int
    lab_id: int

    # lab_name不是equipments表字段，由Router根据已加载的equipment.lab补充。
    lab_name: str | None = None

    name: str
    description: str | None = None
    img: str | None = None
    spec: str | None = None
    quantity: int
    status: int
    created_at: datetime
    updated_at: datetime


class EquipmentCreateRequest(BaseModel):
    """管理员新增设备时允许提交的字段。"""

    lab_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    img: str | None = Field(default=None, max_length=500)
    spec: str | None = Field(default=None, max_length=100)
    quantity: int = Field(default=1, ge=1, le=999)
    status: Literal[0, 1] = 1


class EquipmentUpdateRequest(BaseModel):
    """管理员PATCH设备时允许提交的字段。"""

    lab_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    img: str | None = Field(default=None, max_length=500)
    spec: str | None = Field(default=None, max_length=100)
    quantity: int | None = Field(default=None, ge=1, le=999)
    status: Literal[0, 1] | None = None


class EquipmentPageResponse(BaseModel):
    """设备分页接口data内部的结构。"""

    list: list[EquipmentResponse]
    total: int

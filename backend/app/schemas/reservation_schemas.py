"""预约创建、审核、返回与分页所使用的 Pydantic 模型。"""

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReservationCreateRequest(BaseModel):
    """登录用户提交实验室或设备预约时允许提供的字段。"""

    lab_id: int = Field(gt=0)
    equipment_id: int | None = Field(default=None, gt=0)
    date: date
    start_time: time
    end_time: time
    remark: str | None = Field(default=None, max_length=255)


class ReservationResponse(BaseModel):
    """预约列表中单条记录允许返回给前端的字段。"""

    # 允许model_validate()从SQLAlchemy Reservation对象读取同名属性。
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    # 这些展示字段不是Reservation本表属性。先给默认值，model_validate()完成后
    # 再由Router使用已经预加载的relationship补充。
    user_name: str | None = None
    lab_id: int
    lab_name: str | None = None
    equipment_id: int | None = None
    equipment_name: str | None = None

    # type不是数据库字段，由Router根据equipment_id计算。
    type: Literal["实验室", "设备"] | None = None

    # 使用真实date/time类型；输出JSON时Pydantic会自动转成ISO字符串。
    date: date
    start_time: time
    end_time: time
    remark: str | None = None
    status: Literal[0, 1, 2, 3]


class ReservationPageResponse(BaseModel):
    """预约分页接口data字段的结构。"""

    list: list[ReservationResponse]
    total: int


class AuditReservationRequest(BaseModel):
    """管理员审核预约时允许提交的状态。"""

    # Literal让1和2以外的值在进入Router前自动得到HTTP 422。
    status: Literal[1, 2]

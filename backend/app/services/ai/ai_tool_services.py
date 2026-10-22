"""AI工具定义与只读数据库工具执行器。

调用链：ai_services.chat()读取模型的function_call，然后调用本模块；
本模块只允许执行AI_TOOLS中公开的只读查询，不允许模型提交任意SQL。
"""

import json
from datetime import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.equipment_models import Equipment
from app.models.lab_models import Lab
from app.services.lab import equipment_services, lab_services

# 这是交给Responses API的工具说明书，不会直接执行任何Python函数。
# 模型只能从这个白名单中选择工具。
AI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "list_open_labs",
        "description": (
            "按名称或位置查询实验室及其状态，可选带上设备清单。默认只返回开放中的实验室；"
            "把include_closed设为true时，已关闭的实验室也会返回（用于回答"
            "“某实验室为什么不能约、它登记了什么设备”这类问题）；"
            "需要比较多间实验室的设备时，把include_equipment设为true，一次就能拿到，"
            "不要逐个实验室调用list_lab_equipments。"
            "开放只表示labs.status=1，不代表某个预约时段仍然空闲。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "可选，按实验室名称或位置模糊搜索",
                },
                "include_closed": {
                    "type": "boolean",
                    "description": "是否连已关闭的实验室一起返回，默认false",
                },
                "include_equipment": {
                    "type": "boolean",
                    "description": "是否同时返回每个实验室登记的设备，默认false",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "description": "最多返回多少条，默认10条",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "list_lab_equipments",
        "description": "根据实验室ID查询该实验室当前登记的设备",
        "parameters": {
            "type": "object",
            "properties": {
                "lab_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "实验室主键ID",
                },
                "keywords": {
                    "type": "string",
                    "description": "可选，按设备名称模糊搜索",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "description": "最多返回多少条，默认20条",
                },
            },
            "required": ["lab_id"],
            "additionalProperties": False,
        },
    },
]


class ListOpenLabsArguments(BaseModel):
    """list_open_labs允许接收的参数白名单。"""

    # extra="forbid"表示模型偷偷多传字段时直接校验失败。
    model_config = ConfigDict(extra="forbid")

    keywords: str | None = Field(default=None, max_length=50)
    include_closed: bool = False
    include_equipment: bool = False
    limit: int = Field(default=10, ge=1, le=20)


class ListLabEquipmentsArguments(BaseModel):
    """list_lab_equipments允许接收的参数白名单。"""

    model_config = ConfigDict(extra="forbid")

    lab_id: int = Field(gt=0)
    keywords: str | None = Field(default=None, max_length=50)
    limit: int = Field(default=20, ge=1, le=20)


def _time_text(value: time | None) -> str | None:
    """把datetime.time转换为可JSON序列化的HH:MM文本。"""

    if value is None:
        return None
    return value.isoformat(timespec="minutes")


def _json_output(data: dict[str, Any]) -> str:
    """生成给模型读取的中文JSON，不输出ASCII转义码。"""

    return json.dumps(data, ensure_ascii=False)


def _parse_arguments(arguments: str) -> dict[str, Any]:
    """把模型返回的JSON字符串解析为对象。"""

    raw = json.loads(arguments or "{}")
    if not isinstance(raw, dict):
        raise ValueError("工具参数必须是JSON对象")
    return raw


async def execute_ai_tool(
    session: AsyncSession,
    *,
    name: str,
    arguments: str,
) -> str:
    """执行白名单中的只读工具，并返回可回填给模型的JSON字符串。"""

    # 参数JSON损坏或字段类型不正确属于可预期的模型调用错误。
    # 把错误作为工具结果回喂模型，模型可以修正参数或向用户解释。
    try:
        raw_arguments = _parse_arguments(arguments)
    except (json.JSONDecodeError, ValueError) as exc:
        return _json_output(
            {
                "ok": False,
                "error": "invalid_arguments",
                "message": str(exc),
            }
        )

    if name == "list_open_labs":
        try:
            data = ListOpenLabsArguments.model_validate(raw_arguments)
        except ValidationError as exc:
            return _json_output(
                {
                    "ok": False,
                    "error": "invalid_arguments",
                    "details": exc.errors(include_url=False),
                }
            )

        # 复用现有实验室Service，不在AI模块重复写分页SQL。
        # include_closed=True 时 status 传 None，表示不按状态过滤：关闭的实验室
        # 也必须能被查到，否则“综合开放实验室（status=0）”这类问题模型永远拿不到 ID。
        labs, total = await lab_services.get_lab_page_list(
            session,
            page=1,
            page_size=data.limit,
            keywords=data.keywords,
            status=None if data.include_closed else 1,
        )

        # include_equipment=True 时一次把设备也查出来：比较“哪间实验室有示波器/焊台”
        # 这类问题原本要 1 次实验室查询 + N 次设备查询，模型得多跑一轮，慢 10 秒左右。
        equipment_by_lab: dict[int, list[dict[str, Any]]] = {}
        if data.include_equipment and labs:
            rows = await session.scalars(
                select(Equipment)
                .where(Equipment.lab_id.in_([lab.id for lab in labs]))
                .order_by(Equipment.lab_id, Equipment.id)
            )
            for equipment in rows.all():
                equipment_by_lab.setdefault(equipment.lab_id, []).append(
                    {
                        "id": equipment.id,
                        "name": equipment.name,
                        "spec": equipment.spec,
                        "quantity": equipment.quantity,
                        "status_text": "正常" if equipment.status == 1 else "维修",
                    }
                )

        items: list[dict[str, Any]] = []
        for lab in labs:
            item: dict[str, Any] = {
                "id": lab.id,
                "name": lab.name,
                "location": lab.location,
                "capacity": lab.capacity,
                "open_time": _time_text(lab.open_time),
                "close_time": _time_text(lab.close_time),
                "status": lab.status,
                "status_text": "开放" if lab.status == 1 else "关闭",
                "description": lab.description,
            }
            if data.include_equipment:
                item["equipments"] = equipment_by_lab.get(lab.id, [])
            items.append(item)

        return _json_output(
            {
                "ok": True,
                "meaning": (
                    "status=1表示后台启用，0表示已关闭；两者都不表示预约时段空闲"
                    if data.include_closed
                    else "status=1，仅表示后台启用，不表示预约时段空闲"
                ),
                "total": total,
                "items": items,
            }
        )

    if name == "list_lab_equipments":
        try:
            data = ListLabEquipmentsArguments.model_validate(raw_arguments)
        except ValidationError as exc:
            return _json_output(
                {
                    "ok": False,
                    "error": "invalid_arguments",
                    "details": exc.errors(include_url=False),
                }
            )

        # 先区分“实验室不存在”和“实验室存在但没有设备”。
        lab = await session.get(Lab, data.lab_id)
        if lab is None:
            return _json_output(
                {
                    "ok": False,
                    "error": "lab_not_found",
                    "message": "指定实验室不存在",
                }
            )

        # 复用现有设备Service，统一使用已经验证的关键词、实验室和分页条件，
        # 不在AI工具里再写一份设备查询SQL。
        equipments, total = await equipment_services.get_equipment_page_list(
            session,
            page=1,
            page_size=data.limit,
            keywords=data.keywords,
            lab_id=data.lab_id,
        )
        return _json_output(
            {
                "ok": True,
                "lab": {"id": lab.id, "name": lab.name},
                "total": total,
                "items": [
                    {
                        "id": equipment.id,
                        "name": equipment.name,
                        "spec": equipment.spec,
                        "quantity": equipment.quantity,
                        "status": equipment.status,
                        "status_text": "正常" if equipment.status == 1 else "维修",
                        "description": equipment.description,
                    }
                    for equipment in equipments
                ],
            }
        )

    # 即使模型伪造了一个函数名，也不会通过globals()、eval()或动态导入执行。
    return _json_output(
        {
            "ok": False,
            "error": "unknown_tool",
            "message": f"不支持的工具：{name}",
        }
    )

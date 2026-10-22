"""Agent工具白名单：只读查询 + 创建待确认预约草稿。"""

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessException
from app.schemas.ai_schemas import PendingReservationAction
from app.schemas.reservation_schemas import ReservationCreateRequest
from app.services.ai import ai_action_services, decision_services
from app.services.ai.ai_tool_services import AI_TOOLS, execute_ai_tool

PREPARE_RESERVATION_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "prepare_reservation",
    "description": (
        "根据用户给出的实验室、日期和时段创建待确认预约草稿。"
        "本工具不会创建真实预约；用户仍需在前端确认卡片中点击确认。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "lab_id": {"type": "integer", "minimum": 1},
            "equipment_id": {"type": "integer", "minimum": 1},
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "start_time": {"type": "string", "description": "HH:MM"},
            "end_time": {"type": "string", "description": "HH:MM"},
            "remark": {"type": "string", "maxLength": 255},
        },
        "required": ["lab_id", "date", "start_time", "end_time"],
        "additionalProperties": False,
    },
}

AGENT_TOOLS: list[dict[str, Any]] = [*AI_TOOLS, PREPARE_RESERVATION_TOOL]


@dataclass(slots=True)
class AgentToolResult:
    """工具回填给模型的JSON，以及可选前端确认卡片。"""

    output: str
    pending_action: PendingReservationAction | None = None


def _json_output(data: dict[str, Any]) -> str:
    """把工具结果序列化为模型可读且保留中文的 JSON 字符串。"""

    return json.dumps(data, ensure_ascii=False)


async def execute_agent_tool(
    session: AsyncSession,
    *,
    user_id: int,
    chat_session_id: int,
    name: str,
    arguments: str,
    user_message: str = "",
) -> AgentToolResult:
    """只允许执行注册在AGENT_TOOLS中的工具。

    ``user_message`` 是本轮用户原话，仅用于决策能力核验预约参数来源。
    """

    if name != "prepare_reservation":
        # 教程23的执行器自身也会拦截未知工具名。
        output = await execute_ai_tool(
            session,
            name=name,
            arguments=arguments,
        )
        return AgentToolResult(output=output)

    try:
        raw = json.loads(arguments or "{}")
        if not isinstance(raw, dict):
            raise ValueError("工具参数必须是JSON对象")
        data = ReservationCreateRequest.model_validate(raw)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        return AgentToolResult(
            output=_json_output(
                {
                    "ok": False,
                    "error": "invalid_arguments",
                    "message": str(exc),
                }
            )
        )

    # 结构性校验只保证参数"合法"，保证不了"是用户说的"。这里请 decision 能力
    # 再核验一次参数来源；该能力未配置或调用失败时返回 None，等价于放行。
    verdict = await decision_services.verify_reservation_params(
        session,
        chat_session_id=chat_session_id,
        user_message=user_message,
        data=data,
    )
    if verdict is not None and not verdict.approve:
        missing = "、".join(verdict.unsupported_fields) or "关键信息"
        reason = verdict.reason.strip() or "部分参数缺少用户明确说明"
        return AgentToolResult(
            output=_json_output(
                {
                    "ok": False,
                    "error": "reservation_params_unconfirmed",
                    "message": (
                        f"以下信息用户尚未明确说明：{missing}（{reason}）。"
                        "请先向用户确认这些信息，不要自行假设。"
                    ),
                    "unsupported_fields": verdict.unsupported_fields,
                }
            )
        )

    try:
        pending_action = await ai_action_services.prepare_reservation_action(
            session,
            user_id=user_id,
            chat_session_id=chat_session_id,
            data=data,
        )
    except BusinessException as exc:
        # 只返回经过业务层定义的安全中文message，不返回SQL和内部异常。
        return AgentToolResult(
            output=_json_output(
                {
                    "ok": False,
                    "error": "reservation_rejected",
                    "message": exc.message,
                }
            )
        )

    output_data = pending_action.model_dump(mode="json")
    return AgentToolResult(
        output=_json_output(
            {
                "ok": True,
                "message": "预约草稿已生成，必须等待用户在前端确认后才会提交",
                "pending_action": output_data,
            }
        ),
        pending_action=pending_action,
    )

"""决策（decision）：生成预约草稿前，核验参数是不是用户真的说过。

确定性校验（``validate_reservation_request``）只能判断"参数是否合法"，
判断不了"参数是不是模型自己编的"——用户只说"帮我约明天下午"，
模型照样能填出一个 14:00-15:00 并通过全部结构性校验。

本模块把这项语义判断交给 ``decision`` 能力承担。同样是**可选增强**：
未配置、调用失败或输出无法解析时返回 ``None``，调用方按"放行"处理，
行为退回到加该能力之前的状态。

两条调用路径（按模型名自动选择）：

1. 百炼专用决策模型 ``decision-model-preview``：
   走 **TypeSafe System One**（``POST /compatible-mode/v1/systemone``），
   一次前向对每个字段返回 P(用户明确说过)，不生成文本。
2. 其它文本模型：走项目统一的 Responses API，让它输出 JSON 裁决。
"""

import json
import logging
import re

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.equipment_models import Equipment
from app.models.lab_models import Lab
from app.schemas.reservation_schemas import ReservationCreateRequest
from app.services.ai import ai_provider_services, ai_usage_services, chat_services
from app.services.ai.providers import get_provider
from app.services.ai.providers.base import ChatResult

logger = logging.getLogger(__name__)

DECISION_MAX_OUTPUT_TOKENS = 1024
# 决策失败只是少一道兜底，不该让用户一直等，因此超时也压得比较短。
DECISION_DEFAULT_TIMEOUT = 20.0
# 取最近多少条消息作为判断依据；够覆盖"几点？——下午三点"这种多轮补全即可。
DECISION_HISTORY_LIMIT = 8
_HISTORY_ITEM_CHARS = 300

# 百炼「决策模型」专用接口。
BAILIAN_DECISION_MODEL = "decision-model-preview"
DECISION_SYSTEMONE_PATH = "/systemone"
# 「完全没提时刻」的判定阈值：开始与结束两个概率**都**低于它才拦。
# 实测（2026-10-20，只看用户原话）：
#   「帮我约明天下午的实验室」   start 0.11 / end 0.06 → 拦（对）
#   「帮我约明天下午三点」      start 0.61 / end 0.13 → 放（只说了开始，按保守规则不拦）
#   「帮我约明天两点到三点」     start 0.87 / end 0.81 → 放（对）
#   「帮我约明天十点到十一点」    start 0.61 / end 0.04 → 放（对，中文数字结尾时刻模型判不准）
#   「帮我约明天四点半到六点」    start 0.49 / end 0.45 → 放（对）
DECISION_NO_TIME_THRESHOLD = 0.35

# 只问两个客观的抽取问题：原话里有没有「开始」时刻、有没有「结束」时刻。
# 为什么这么问：决策模型擅长"从文本里判有无"，不擅长"这句话是否支撑那个参数"。
# 实测（2026-10-20）逐字段问"用户是否明确说明了开始时刻"，会把「只说下午」判成
# 已明确（0.88）；而抽取式问法判别很干净，且能区分"只给了开始、没给结束"。
# 关键措辞：明确要求"只给一个时刻、没说它是开始还是结束"时回答否，
# 否则模型会把「三点」同时算作开始和结束。
DECISION_START_TIME_QUESTION = (
    "用户原话里有没有出现「开始」的具体时钟时刻（例如「两点开始」「14:00」）？"
    "如果用户只给了一个时刻、没说它是开始还是结束，回答否；"
    "只出现「上午/下午」这类模糊时段也算否。"
)
DECISION_END_TIME_QUESTION = (
    "用户原话里有没有出现「结束」的具体时钟时刻（例如「到三点」「16:00 结束」）？"
    "如果用户只给了一个时刻、没说它是开始还是结束，回答否；"
    "只出现「上午/下午」这类模糊时段也算否。"
)

_JSON_OBJECT = re.compile(r"\{.*\}", re.S)

DECISION_INSTRUCTION = """你是"AI智能实验室预约系统"的预约参数核验器。只输出一个 JSON 对象，不要输出任何解释或 Markdown 代码块。

任务：判断【候选预约参数】中的每个字段，能否被【对话记录】中用户的明确表述支撑。

字段名固定为：lab_id、equipment_id、date、start_time、end_time、remark。

判断规则：
1. 只有用户明确说过该信息才算有支撑；由助手自己补全、推断或默认填写的，一律无支撑。
2. 用户说"下午"只能确定是下午，确定不了具体几点，因此 start_time 与 end_time 无支撑。
3. "明天""下周三"这类相对日期，只要能在当前日期基础上换算成具体日期，就算有支撑。
4. 用户没有提到设备时 equipment_id 为空不算缺失，不需要列入 unsupported_fields。
5. 参数之间自相矛盾（如结束时间早于开始时间）时，把相关字段列为无支撑。
6. 保守判断：拿不准时按"无支撑"处理。

输出格式：
{"approve": 布尔, "unsupported_fields": ["字段名", ...], "reason": "一句话理由"}
unsupported_fields 为空时 approve 必须为 true。
"""


class DecisionVerdict(BaseModel):
    """一次参数核验的裁决结果。"""

    approve: bool = True
    unsupported_fields: list[str] = Field(default_factory=list)
    reason: str = ""


def _extract_json(raw: str) -> dict[str, object] | None:
    """从可能带解释文字的模型输出中提取首个 JSON 对象。"""

    text = (raw or "").strip()
    if not text:
        return None
    match = _JSON_OBJECT.search(text)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def parse_verdict(raw: str) -> DecisionVerdict | None:
    """解析模型输出；结构不合法时返回 None，由调用方按放行处理。"""

    payload = _extract_json(raw)
    if payload is None:
        return None
    try:
        verdict = DecisionVerdict.model_validate(payload)
    except ValidationError:
        return None
    # 防止模型自相矛盾：列了缺失字段却给 approve=true。以字段列表为准。
    if verdict.unsupported_fields:
        verdict.approve = False
    return verdict


def _build_state_text(
    *,
    history: list[tuple[str, str]],
    user_message: str,
    data: ReservationCreateRequest,
    lab_name: str,
    equipment_name: str | None,
) -> str:
    """拼出决策模型要看的对话记录与候选参数（两条路径共用）。"""

    lines: list[str] = ["【对话记录】"]
    for role, content in history:
        speaker = "用户" if role == "user" else "助手"
        lines.append(f"{speaker}：{content[:_HISTORY_ITEM_CHARS]}")
    lines.append(f"用户：{user_message[:_HISTORY_ITEM_CHARS]}")
    lines.append("")
    lines.append("【候选预约参数】")
    lines.append(f"实验室：{lab_name}（lab_id={data.lab_id}）")
    if equipment_name is None:
        lines.append("设备：无（equipment_id 为空）")
    else:
        lines.append(f"设备：{equipment_name}（equipment_id={data.equipment_id}）")
    lines.append(f"日期：{data.date.isoformat()}（date）")
    lines.append(f"开始时间：{data.start_time.strftime('%H:%M')}（start_time）")
    lines.append(f"结束时间：{data.end_time.strftime('%H:%M')}（end_time）")
    lines.append(f"备注：{data.remark or '（空）'}（remark）")
    return "\n".join(lines)


def _build_conversation_text(
    *,
    history: list[tuple[str, str]],
    user_message: str,
) -> str:
    """只拼用户原话与对话记录。

    专门给专用决策模型用：实测把候选参数一起放进 state，模型会把它们当成
    "用户说过"的证据（同一句话的 P(有具体时刻) 从 0.27 涨到 0.88）。
    """

    lines: list[str] = []
    for role, content in history:
        speaker = "用户" if role == "user" else "助手"
        lines.append(f"{speaker}：{content[:_HISTORY_ITEM_CHARS]}")
    lines.append(f"用户：{user_message[:_HISTORY_ITEM_CHARS]}")
    return "\n".join(lines)


async def _decide_with_systemone(
    config: ai_provider_services.CapabilityConfig,
    *,
    state_text: str,
) -> tuple[DecisionVerdict | None, ChatResult]:
    """调用百炼决策模型（TypeSafe System One），只核验"用户有没有说出具体时刻"。

    ``state_text`` 这里只应传入**用户原话**：把候选参数一起塞进 state 会让模型
    把它们当成"用户说过"的证据（实测 probabilities 会从 0.27 涨到 0.88）。
    """

    payload = {
        "model": config.model.strip(),
        "state": state_text,
        "questions": {
            "has_start_time": {
                "type": "noul",
                "instructions": DECISION_START_TIME_QUESTION,
            },
            "has_end_time": {
                "type": "noul",
                "instructions": DECISION_END_TIME_QUESTION,
            },
        },
    }
    url = config.base_url.rstrip("/") + DECISION_SYSTEMONE_PATH
    timeout = config.timeout_seconds or DECISION_DEFAULT_TIMEOUT
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": "Bearer " + config.api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        body = response.json()

    answers = body.get("answers") or {}

    usage = body.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    result = ChatResult(text="", input_tokens=input_tokens, total_tokens=input_tokens)

    unsupported: list[str] = []
    details: list[str] = []
    probabilities: dict[str, float] = {}
    for field, answer_key in (("start_time", "has_start_time"), ("end_time", "has_end_time")):
        probability = (answers.get(answer_key) or {}).get("noul")
        if probability is None:
            # 模型没给这一项：不拦，避免因响应残缺误伤正常预约。
            logger.warning("decision model returned no %s answer; skipping field", answer_key)
            continue
        value = float(probability)
        probabilities[field] = value
        details.append(f"{field} {value:.2f}")

    # 只在「开始和结束都没有任何信号」时才拦 —— 也就是用户压根没提具体时刻。
    # 不因为单个字段偏低就拦：实测模型对中文数字时刻很不稳定
    # （「两点到三点」的结束能给 0.79，但「十点到十一点」的结束只有 0.04，
    # 「四点半到六点」两项只有 0.49/0.45），单字段判定会误拦正常预约。
    if probabilities and all(
        value < DECISION_NO_TIME_THRESHOLD for value in probabilities.values()
    ):
        unsupported = ["start_time", "end_time"]

    if not unsupported:
        return DecisionVerdict(approve=True), result

    return (
        DecisionVerdict(
            approve=False,
            unsupported_fields=unsupported,
            reason="用户原话里没有提到具体时刻（模型支持概率 " + "，".join(details) + "）",
        ),
        result,
    )


async def _decide_with_generic_model(
    config: ai_provider_services.CapabilityConfig,
    *,
    state_text: str,
) -> tuple[DecisionVerdict | None, ChatResult]:
    """调用通用文本模型（Responses API + JSON 提示词）。"""

    provider_impl = get_provider(config.provider)
    result = await provider_impl.create_response(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.timeout_seconds or DECISION_DEFAULT_TIMEOUT,
        model=config.model.strip(),
        instructions=DECISION_INSTRUCTION,
        input=state_text,
        max_output_tokens=DECISION_MAX_OUTPUT_TOKENS,
        # 核验同样是短判定任务，不需要思考链。
        reasoning_effort=None,
        dashscope_base_url=config.dashscope_base_url,
    )
    return parse_verdict(result.text), result


async def verify_reservation_params(
    db: AsyncSession,
    *,
    chat_session_id: int,
    user_message: str,
    data: ReservationCreateRequest,
) -> DecisionVerdict | None:
    """核验预约参数是否都有用户原话支撑；未配置或失败时返回 None（放行）。"""

    config = await ai_provider_services.get_capability_config(db, "decision")
    if config is None or not config.api_key or not config.model.strip():
        # 没配置就是没启用，静默返回，不算错误。
        return None

    # 当前这一轮的用户消息还没落库（要等模型回答完才一起保存），所以单独传入。
    history = await chat_services.load_history(
        db,
        session_id=chat_session_id,
        limit=DECISION_HISTORY_LIMIT,
    )

    lab = await db.get(Lab, data.lab_id)
    lab_name = lab.name if lab is not None else f"实验室#{data.lab_id}"
    equipment_name: str | None = None
    if data.equipment_id is not None:
        equipment = await db.get(Equipment, data.equipment_id)
        equipment_name = equipment.name if equipment is not None else f"设备#{data.equipment_id}"

    state_text = _build_state_text(
        history=history,
        user_message=user_message,
        data=data,
        lab_name=lab_name,
        equipment_name=equipment_name,
    )

    is_systemone_model = config.model.strip() == BAILIAN_DECISION_MODEL
    try:
        if is_systemone_model:
            # 专用模型只看用户原话，不能把候选参数喂进去。
            verdict, result = await _decide_with_systemone(
                config,
                state_text=_build_conversation_text(
                    history=history,
                    user_message=user_message,
                ),
            )
        else:
            verdict, result = await _decide_with_generic_model(config, state_text=state_text)
    except Exception:
        # 决策模型挂了不能连带把 AI 预约功能搞停；退回放行并留日志。
        logger.warning("reservation decision failed; allowing draft creation", exc_info=True)
        return None

    await ai_usage_services.record_usage(
        db,
        capability="decision",
        provider=config.provider,
        model=config.model,
        result=result,
        commit=False,
    )

    if verdict is None:
        logger.warning(
            "decision output was not recognized; allowing draft creation raw=%r",
            (result.text or "")[:200],
        )
    return verdict

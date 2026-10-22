"""LangGraph编排：使用现有Responses供应商执行Agent循环。

[链路定位] 本文件用状态图表达"模型 → 工具 → 模型"的循环，是 Agent 的"大脑"，
但自己不写数据库、不解析模型响应（那些由 providers 和 agent_tool_services 负责）：

    上游：ai_services.chat() 调用 build_agent_graph() 后 graph.ainvoke(...) 启动一次
    图内节点：agent(调模型) → tools(顺序执行白名单工具) → agent 或 finalize(强制收尾)
    下游：agent_tool_services.execute_agent_tool()  —— 真正执行工具（只读查询/预约草稿）
          providers.ChatProvider.create_response() / stream_response()  —— 真正调模型
    约束：MAX_TOOL_ROUNDS=5 限制工具轮次；recursion_limit=10 是图级安全网。

[ReAct口径] 这是一种“ReAct风格”的工具循环：模型根据当前上下文决定动作
(function/tool call)，服务端执行后把观察结果(function_call_output)交还模型，模型再
继续决定或回答。但它不是论文/教程里用提示词显式输出``Thought -> Action ->
Observation``的经典文本ReAct，也没有调用LangGraph预置的``create_react_agent``。
本项目用原生Function Calling + 自建StateGraph实现同一类“推理/行动交替”控制流，
内部推理不应展示或持久化。面试时应说“LangGraph实现的ReAct-style工具调用循环”，
不要说“直接使用了LangGraph官方ReAct Agent模板”。
"""

from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.ai_schemas import PendingReservationAction
from app.services.ai.agent_tool_services import AGENT_TOOLS, execute_agent_tool
from app.services.ai.providers.base import ChatProvider, ChatResult, ToolCall

MAX_TOOL_ROUNDS = 5

# finalize 阶段追加的用户指令：这一轮已经不允许再调工具，必须明确告诉模型
# “不要输出工具调用语法”。否则模型会把调用写成正文（第 5 题的真实故障）。
FINALIZE_INSTRUCTION = (
    "请直接用自然语言总结并回答上面的问题，不要再输出任何工具调用语法"
    "（<tool_call>、<invoke>、]<]minimax[>[ 之类一律不要出现）。"
    "如果已有工具结果不足以回答，就直接说明缺少哪些信息，不要编造。"
)

# 工具英文名 → 页面上给人看的中文过程文案。没有映射时退回英文名，
# 这样新加工具不会因为忘记登记就把过程区留空。
TOOL_LABELS = {
    "list_open_labs": "查询开放实验室",
    "list_lab_equipments": "查询实验室设备",
    "prepare_reservation": "整理预约草稿",
}

# 过程事件回调：节点每产生一条事件就 await 一次，由上层决定怎么送出去。
# 用回调而不是让节点自己 yield —— LangGraph 的节点返回值就是状态更新，
# 在节点里 yield 拿不到，只能靠外部注入的 sink。
Emit = Callable[[dict[str, Any]], Awaitable[None]]


class AgentState(TypedDict):
    """LangGraph 节点之间传递的显式状态结构。

    ``model_input`` 保留供应商原始 response items；``pending_tool_calls`` 是下一节点要
    执行的调用；``pending_action`` 是交给前端确认而非立即写库的高影响动作。
    """

    # Responses完整输出对象也会进入列表，因此不能只标注成dict。
    model_input: list[Any]
    pending_tool_calls: list[ToolCall]
    model_results: list[ChatResult]
    used_tools: list[str]
    rounds: int
    final_text: str
    pending_action: PendingReservationAction | None


def build_agent_graph(
    *,
    db: AsyncSession,
    user_id: int,
    chat_session_id: int,
    provider: ChatProvider,
    provider_kwargs: dict[str, Any],
    emit: Emit | None = None,
    tools: list[dict[str, Any]] | None = None,
    user_message: str = "",
):
    """构建当前HTTP请求使用的异步Agent图。

    ``emit`` 为空时行为与第24节完全一致（整包返回、不产生任何事件），
    所以旧的 POST /api/ai/chat 不需要任何改动就能继续用。

    ``tools`` 为 None 表示不限制（用全部工具）；传空列表表示本轮不给工具，
    由意图识别裁剪。``user_message`` 是本轮用户原话，供决策能力核验预约参数。
    """

    active_tools = AGENT_TOOLS if tools is None else tools

    async def agent_node(state: AgentState) -> dict[str, Any]:
        """调用模型一次，并把文本或工具调用写回图状态。

        在ReAct类比中，这一步负责“根据已有消息和工具观察决定下一步”：
        返回tool_calls就是选择Action；返回最终文本就是结束。服务端不会要求模型
        输出或记录显式Thought，避免把内部推理当成可信业务数据或暴露给前端。
        """

        if emit is not None:
            # 第一轮是"在想"，之后每一轮是"拿着工具结果继续想"，文案区分开
            await emit(
                {
                    "type": "status",
                    "message": "正在思考…" if state["rounds"] == 0 else "正在整理查询结果…",
                }
            )
        request = {
            **provider_kwargs,
            "input": state["model_input"],
            # 空列表统一转成 None：供应商适配器用 `if tools:` 判空，
            # 传 None 才是"本轮不带工具"，传 [] 会让部分网关报参数错误。
            "tools": active_tools or None,
            "tool_choice": "auto" if active_tools else None,
        }
        if emit is None:
            result = await provider.create_response(**request)
        else:

            async def on_delta(text: str) -> None:
                """把供应商文本增量转换成上层统一的 token 事件。"""

                await emit({"type": "token", "content": text})

            result = await provider.stream_response(on_delta=on_delta, **request)
        return {
            "pending_tool_calls": result.tool_calls,
            "model_results": [*state["model_results"], result],
            "rounds": state["rounds"] + 1,
            "final_text": result.text.strip() if not result.tool_calls else "",
        }

    def route_after_agent(state: AgentState) -> Literal["tools", "__end__"]:
        """有工具调用就进入 tools；已有最终文本则结束本轮图。"""

        return "tools" if state["pending_tool_calls"] else END

    async def tools_node(state: AgentState) -> dict[str, Any]:
        """顺序执行白名单工具，并按 Responses 协议回填工具结果。

        在ReAct类比中，白名单工具调用是Action，``function_call_output``是
        Observation。Observation只是一段工具结果，下一轮仍由agent节点判断它是否
        足够回答；工具节点自己不生成最终自然语言答案。
        """

        model_input = list(state["model_input"])
        used_tools = list(state["used_tools"])
        pending_action = state["pending_action"]

        # MiniMax要求后续工具轮次保留上一轮完整输出；这同时保留
        # reasoning、message和function_call，不能只手工重建函数调用。
        model_input.extend(state["model_results"][-1].response_items)

        # 同一个AsyncSession内顺序执行，避免并发Session操作。
        for tool_call in state["pending_tool_calls"]:
            label = TOOL_LABELS.get(tool_call.name, tool_call.name)
            if emit is not None:
                await emit({"type": "tool_start", "name": tool_call.name, "label": label})
            tool_result = await execute_agent_tool(
                db,
                user_id=user_id,
                chat_session_id=chat_session_id,
                name=tool_call.name,
                arguments=tool_call.arguments,
                user_message=user_message,
            )
            if tool_call.name not in used_tools:
                used_tools.append(tool_call.name)
            if tool_result.pending_action is not None:
                pending_action = tool_result.pending_action

            if emit is not None:
                # 只给短预览：完整结果已经在 model_input 里给模型用了，
                # 把整段 JSON 推到前端过程区既读不了也拖慢渲染。
                output = tool_result.output
                preview = output if len(output) <= 200 else f"{output[:200]}…"
                await emit(
                    {
                        "type": "tool_end",
                        "name": tool_call.name,
                        "label": label,
                        "preview": preview,
                    }
                )

            model_input.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": tool_result.output,
                }
            )

        return {
            "model_input": model_input,
            "pending_tool_calls": [],
            "used_tools": used_tools,
            "pending_action": pending_action,
        }

    def route_after_tools(state: AgentState) -> Literal["agent", "finalize"]:
        """未到轮次上限时让模型继续推理，否则强制进入收尾节点。"""

        return "agent" if state["rounds"] < MAX_TOOL_ROUNDS else "finalize"

    async def finalize_node(state: AgentState) -> dict[str, Any]:
        """达到工具轮次上限后禁止新调用，强制生成自然语言答案。"""

        if emit is not None:
            await emit({"type": "status", "message": "正在组织回答…"})
        request = {
            **provider_kwargs,
            # 追加一句“不要再调工具”的收尾指令：tools 传了但 tool_choice="none"，
            # 部分模型仍会把调用写进正文，这里把边界说清楚。
            "input": [*state["model_input"], {"role": "user", "content": FINALIZE_INSTRUCTION}],
            "tools": active_tools or None,
            # 最后一轮禁止再调工具：轮次上限到了也要给用户一个成型的回答
            "tool_choice": "none" if active_tools else None,
        }
        if emit is None:
            result = await provider.create_response(**request)
        else:

            async def on_delta(text: str) -> None:
                """把收尾回答的文本增量继续转发给 SSE 上层。"""

                await emit({"type": "token", "content": text})

            result = await provider.stream_response(on_delta=on_delta, **request)
        return {
            "pending_tool_calls": [],
            "model_results": [*state["model_results"], result],
            "final_text": result.text.strip(),
        }

    # LangGraph在本项目的具体价值不是“替模型思考”，而是把原本容易散落在while
    # 循环中的状态、分支和停止条件显式化：agent有调用就去tools，没有就结束；
    # tools未超轮次就回agent，超限就去finalize。compile()得到可ainvoke的执行图。
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_node("finalize", finalize_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route_after_agent)
    builder.add_conditional_edges("tools", route_after_tools)
    builder.add_edge("finalize", END)
    return builder.compile()

"""AI对话会话与消息的业务查询、写入。

职责：会话的创建/读取/清空/删除，以及历史消息的加载与保存。
MiniMax的Responses API不支持previous_response_id，多轮上下文由本模块从数据库
读历史messages拼进input，由ai_services.chat调用。
"""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_models import ChatMessage, ChatSession
from app.schemas.ai_schemas import ChatMessageItem, ChatSessionDetail, ChatSessionSummary

# 一次读取历史消息的最大条数，避免极长会话把上下文撑爆。
# MiniMax M3.1-Flash 上下文窗口 1M，但每次请求仍受 token 上限约束；按条数
# 截断是廉价的安全网，真正上限取决于每条消息的字符数。
HISTORY_LOAD_LIMIT = 200


def _make_title(first_message: str) -> str:
    """用首条用户消息的前30个字符作为会话标题。"""
    return (first_message.strip().replace("\n", " ") or "新对话")[:30]


async def get_or_create_session(
    db: AsyncSession,
    *,
    user_id: int,
    session_id: int | None,
    first_message: str,
) -> ChatSession:
    """有session_id则读取并校验归属，无则创建新会话。"""

    if session_id is not None:
        session = await db.get(ChatSession, session_id)
        if session is None or session.user_id != user_id:
            # 会话不存在或不属于当前用户，按不存在处理，防止越权读取他人会话。
            raise ValueError("会话不存在")
        return session

    session = ChatSession(user_id=user_id, title=_make_title(first_message))
    db.add(session)
    try:
        # 需要拿到自增主键ID，因此显式flush；失败回滚。
        await db.flush()
    except Exception:
        await db.rollback()
        raise
    return session


async def load_history(
    db: AsyncSession,
    *,
    session_id: int,
    limit: int = HISTORY_LOAD_LIMIT,
) -> list[tuple[str, str]]:
    """按时间升序返回 (role, content)，供模型拼进input。

    ``limit`` 默认 ``HISTORY_LOAD_LIMIT``：超过上限时只取最近 ``limit`` 条
    （同一会话内仍按时间升序），防止极长会话撑爆模型上下文或拖慢请求。
    """

    statement = (
        select(ChatMessage.role, ChatMessage.content, ChatMessage.id)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    rows = (await db.execute(statement)).all()
    # 反转回时间升序，确保模型按时间线读历史。
    return [(row.role, row.content) for row in reversed(rows)]


async def save_message(
    db: AsyncSession,
    *,
    session_id: int,
    role: str,
    content: str,
) -> None:
    """追加一条消息（user或assistant）。单条写入的入口保留，调用方应保证
    异常时的回滚语义与 ``save_round`` 一致。"""

    db.add(ChatMessage(session_id=session_id, role=role, content=content))
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def save_round(
    db: AsyncSession,
    *,
    session_id: int,
    user_content: str,
    assistant_content: str,
    commit: bool = True,
) -> None:
    """把本轮的 user + assistant 消息与会话 updated_at 写入数据库。

    单次事务内同时插入两条消息并刷新会话时间戳；任一写入失败整体回滚，
    避免出现"用户消息已落库、助手回答缺失"的半条会话。会话活跃时间直接
    用 Python ``datetime.now(UTC)``，而非依赖 ORM ``onupdate=func.now()``，
    因为 ``onupdate`` 只在 UPDATE 时才会刷新，而本流程内 UPDATE ChatSession
    之前必须 flush，确保 user/assistant 两行已拿到自增主键。
    """

    session = await db.get(ChatSession, session_id)
    if session is None:
        raise RuntimeError("写入消息时会话已不存在")
    db.add_all(
        [
            ChatMessage(session_id=session_id, role="user", content=user_content),
            ChatMessage(session_id=session_id, role="assistant", content=assistant_content),
        ]
    )
    session.updated_at = datetime.now(UTC)
    try:
        if commit:
            await db.commit()
        else:
            # 由上层把消息和用量记录放进同一事务后统一提交。
            await db.flush()
    except Exception:
        await db.rollback()
        raise


async def list_sessions(
    db: AsyncSession,
    *,
    user_id: int,
) -> list[ChatSessionSummary]:
    """返回当前用户的会话摘要列表，按最后活跃时间倒序。"""

    statement = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = (await db.scalars(statement)).all()
    return [ChatSessionSummary(id=s.id, title=s.title, updated_at=s.updated_at) for s in sessions]


async def get_session_detail(
    db: AsyncSession,
    *,
    user_id: int,
    session_id: int,
) -> ChatSessionDetail | None:
    """返回会话详情；不存在或不属于当前用户时返回None。"""

    session = await db.get(ChatSession, session_id)
    if session is None or session.user_id != user_id:
        return None
    history = await load_history(db, session_id=session_id)
    return ChatSessionDetail(
        id=session.id,
        title=session.title,
        messages=[ChatMessageItem(role=r, content=c) for r, c in history],
    )


async def clear_session(
    db: AsyncSession,
    *,
    user_id: int,
    session_id: int,
) -> bool:
    """清空会话全部消息但保留会话本身；返回是否成功。"""

    session = await db.get(ChatSession, session_id)
    if session is None or session.user_id != user_id:
        return False
    try:
        await db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
        # 重新打开会话时，把 updated_at 刷新到当前时间，让列表页立即把它
        # 排到最前面，避免"清空后仍按老时间沉在下面"。
        from datetime import UTC, datetime

        session.updated_at = datetime.now(UTC)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return True


async def rename_session(
    db: AsyncSession,
    *,
    user_id: int,
    session_id: int,
    title: str,
) -> bool:
    """修改会话标题；返回是否成功（不存在或不属于本人时为False）。

    标题原本只在建会话时由首条提问截断生成，用户没法改成自己认得的名字。
    这里只改 title 一列，不动消息；归属校验必须做，否则能改别人的会话。
    """

    session = await db.get(ChatSession, session_id)
    if session is None or session.user_id != user_id:
        return False
    session.title = title
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return True


async def delete_session(
    db: AsyncSession,
    *,
    user_id: int,
    session_id: int,
) -> bool:
    """删除会话及其全部消息（级联）；返回是否成功。"""

    session = await db.get(ChatSession, session_id)
    if session is None or session.user_id != user_id:
        return False
    try:
        await db.delete(session)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return True

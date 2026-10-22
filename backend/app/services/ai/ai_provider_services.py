"""AI 供应商能力配置：读取、加密。

把“能力（capability）”与“供应商（provider）”解耦：业务代码按能力名取配置，
优先读数据库（管理员可改、即时生效），数据库无配置时回退 .env。
chat / vision / ocr 走 OpenAI 兼容 Responses API，embedding / rerank 走百炼
DashScope 专有接口；所有能力都通过本模块从数据库读取统一配置。
"""

import base64
import hashlib
import logging
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessException
from app.core.settings import get_settings
from app.db.session import session_factory
from app.models.ai_provider_models import AIProviderConfig
from app.schemas.ai_schemas import ProviderConfigUpsertRequest, ProviderConfigView

settings = get_settings()
logger = logging.getLogger(__name__)
_fallback_key_warning_emitted = False


class CapabilityNotConfiguredError(BusinessException):
    """表示某项 AI 能力没有可用配置，可被聊天入口安全降级处理。"""

    def __init__(self, capability: str, message: str) -> None:
        """记录缺失的能力位，供上层只对该类错误执行降级。"""

        self.capability = capability
        super().__init__(message=message, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


def _fernet_from_seed(seed: str) -> Fernet:
    """从配置密钥稳定派生 Fernet 所需的 32 字节 URL-safe key。"""

    digest = hashlib.sha256(seed.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _primary_fernet() -> Fernet:
    """构造 Fernet 实例；优先使用 AI_CONFIG_ENCRYPTION_KEY。

    - 显式配置 ``AI_CONFIG_ENCRYPTION_KEY`` 时，使用它作为派生源；
    - 未配置时回退到 ``JWT_SECRET_KEY``（旧数据兼容），每个进程只在首次使用时
      记录一条 warning，提示运维尽快配置独立密钥，避免 JWT 轮换
      导致所有入库 AI Key 无法解密。
    """

    global _fallback_key_warning_emitted

    if settings.AI_CONFIG_ENCRYPTION_KEY is not None:
        seed = settings.AI_CONFIG_ENCRYPTION_KEY.get_secret_value()
    else:
        seed = settings.JWT_SECRET_KEY.get_secret_value()
        if not _fallback_key_warning_emitted:
            logger.warning(
                "AI_CONFIG_ENCRYPTION_KEY not configured; "
                "AI provider keys encrypted with JWT secret. "
                "configure AI_CONFIG_ENCRYPTION_KEY to decouple lifetimes.",
            )
            _fallback_key_warning_emitted = True
    return _fernet_from_seed(seed)


def encrypt_api_key(plain: str) -> str:
    """加密明文 API Key，返回可入库的字符串。"""
    return _primary_fernet().encrypt(plain.encode()).decode()


def decrypt_api_key(token: str) -> str | None:
    """解密入库 Key，并兼容启用独立密钥前由 JWT 密钥加密的旧数据。"""

    try:
        return _primary_fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        if settings.AI_CONFIG_ENCRYPTION_KEY is None:
            return None

    # 新增 AI_CONFIG_ENCRYPTION_KEY 后，数据库中可能仍有用 JWT_SECRET_KEY
    # 加密的历史密文。只在主密钥失败时尝试旧密钥，避免配置切换导致全部能力失效。
    legacy_seed = settings.JWT_SECRET_KEY.get_secret_value()
    try:
        return _fernet_from_seed(legacy_seed).decrypt(token.encode()).decode()
    except InvalidToken:
        return None


@dataclass(slots=True)
class CapabilityConfig:
    """某个能力一次调用所需的全部供应商信息。"""

    capability: str
    provider: str
    model: str
    base_url: str
    api_key: str  # 明文，仅内存使用，不落库、不写日志
    # 解析时若数据已配置或派生则保存；为 None 时调用方按 provider 默认行为处理。
    dashscope_base_url: str | None = None
    reasoning_effort: str | None = None
    timeout_seconds: float | None = None
    # 生成参数：None 表示沿用代码默认（不向供应商传该参数）。
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    # 自定义系统提示词：None 表示用代码内置的那份。
    system_prompt: str | None = None
    # 模型上下文窗口；None 表示交给调用方去 MODEL_CATALOG 查。
    context_window: int | None = None


# 各能力的默认超时秒数（数据库未单独配置时使用）。供应商/模型/key/base_url
# 已完全由管理员在数据库配置，这里只提供超时的代码兜底默认。
DEFAULT_TIMEOUTS: dict[str, float] = {
    "chat": 60.0,
    # 轻量对话：只服务寒暄/闲聊这类短回答，可以配更便宜更快的模型。
    # 未配置时自动回退到 chat，不影响任何现有行为。
    "chat_light": 30.0,
    "vision": 90.0,
    "ocr": 90.0,
    "embedding": 60.0,
    "rerank": 30.0,
    # intent/decision 是短判定任务，输出几百 token 就该结束。
    # 给 60 秒会让一次卡住的分类把整个聊天拖死，所以单独压到十几秒；
    # 管理员仍可在配置页用 timeout_seconds 覆盖。
    "intent": 15.0,
    "decision": 20.0,
}


async def _load_row(db: AsyncSession | None, capability: str) -> AIProviderConfig | None:
    """读取启用配置；无请求 Session 时创建短生命周期独立 Session。"""

    statement = select(AIProviderConfig).where(
        AIProviderConfig.capability == capability,
        AIProviderConfig.is_active.is_(True),
    )
    if db is not None:
        return await db.scalar(statement)
    async with session_factory() as session:
        return await session.scalar(statement)


async def get_capability_config(
    db: AsyncSession | None,
    capability: str,
) -> CapabilityConfig | None:
    """只读数据库配置；未配置返回 None（AI 能力未启用，需管理员前端配置）。

    AI 供应商配置（provider/model/base_url/key/effort/timeout）已完全数据库化，
    .env 不再保存；首次部署后需管理员登录配置页填写并保存，AI 才可用。
    """

    row = await _load_row(db, capability)
    if row is None:
        return None

    api_key = decrypt_api_key(row.api_key_encrypted) if row.api_key_encrypted else ""
    timeout = row.timeout_seconds
    if timeout is None:
        timeout = DEFAULT_TIMEOUTS.get(capability, 60.0)

    return CapabilityConfig(
        capability=row.capability,
        provider=row.provider,
        model=row.model,
        base_url=row.base_url,
        dashscope_base_url=row.dashscope_base_url,
        api_key=api_key,
        reasoning_effort=row.reasoning_effort,
        timeout_seconds=timeout,
        temperature=row.temperature,
        top_p=row.top_p,
        max_output_tokens=row.max_output_tokens,
        system_prompt=row.system_prompt,
        context_window=row.context_window,
    )


# 合法的能力与供应商枚举；预留 intent/decision 供后续扩展。
# 合法的能力与供应商枚举。
# chat_light 是"按意图切换模型"用的轻量对话位：闲聊走它，知识问答仍走 chat。
VALID_CAPABILITIES = (
    "chat",
    "chat_light",
    "vision",
    "ocr",
    "embedding",
    "rerank",
    "intent",
    "decision",
)
VALID_PROVIDERS = ("minimax", "bailian")

# 能力与供应商的兼容矩阵必须由后端掌握。前端下拉框只是用户体验层，
# 不能阻止绕过浏览器直接调用 API 保存不受支持的组合。
CAPABILITY_PROVIDERS: dict[str, tuple[str, ...]] = {
    "chat": ("minimax", "bailian"),
    "chat_light": ("minimax", "bailian"),
    "vision": ("minimax", "bailian"),
    "ocr": ("bailian",),
    "embedding": ("bailian",),
    "rerank": ("bailian",),
    "intent": ("minimax", "bailian"),
    "decision": ("minimax", "bailian"),
}


def get_allowed_providers(capability: str) -> tuple[str, ...]:
    """返回某能力允许的供应商；未知能力返回空元组。"""

    return CAPABILITY_PROVIDERS.get(capability, ())


def validate_provider_for_capability(capability: str, provider: str) -> None:
    """拒绝后端尚未实现的“能力 + 供应商”组合。"""

    allowed = get_allowed_providers(capability)
    if provider not in allowed:
        allowed_text = "/".join(allowed) or "无"
        raise BusinessException(
            message=f"{capability} 能力不支持 {provider}，可选供应商：{allowed_text}！Ovo!",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def _mask_api_key(encrypted: str | None) -> tuple[str | None, bool]:
    """把加密密钥脱敏为展示字符串；返回 (掩码, 是否已配置)。"""
    if not encrypted:
        return None, False
    plain = decrypt_api_key(encrypted)
    if plain is None:
        return "（无法解密，可能与当前密钥不一致）", True
    if len(plain) <= 8:
        return "****", True
    return f"{plain[:4]}****{plain[-4:]}", True


async def upsert_config(
    db: AsyncSession,
    *,
    capability: str,
    data: ProviderConfigUpsertRequest,
) -> None:
    """保存/更新某个能力的供应商配置；key非空时加密覆盖，空则保留原值。"""

    if capability not in VALID_CAPABILITIES:
        raise BusinessException(
            message="非法能力！Ovo!",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if data.provider not in VALID_PROVIDERS:
        raise BusinessException(
            message="不支持的供应商！Ovo!",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    validate_provider_for_capability(capability, data.provider)

    row = await db.scalar(select(AIProviderConfig).where(AIProviderConfig.capability == capability))
    is_new = row is None
    provider_changed = row is not None and row.provider != data.provider
    if (is_new or provider_changed) and not (data.api_key or "").strip():
        # 同一家供应商编辑其它参数时可以留空以保留旧 Key；但首次配置或切换
        # 供应商绝不能复用旧供应商密钥，否则表面保存成功、实际调用必然鉴权失败。
        raise BusinessException(
            message="首次配置或切换供应商时必须填写对应的 API Key！Ovo!",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if row is None:
        row = AIProviderConfig(capability=capability)
        db.add(row)

    row.provider = data.provider
    row.model = data.model
    row.base_url = data.base_url
    # dashscope_base_url 为空字符串视为清空，否则保存原样（前端通过提交
    # null/undefined 表示不修改，提交空字符串表示显式清空）。
    if data.provider != "bailian":
        # DashScope 地址只属于百炼；切回 MiniMax 时清掉旧值，避免形成幽灵配置。
        row.dashscope_base_url = None
    elif data.dashscope_base_url == "":
        row.dashscope_base_url = None
    elif data.dashscope_base_url is not None:
        row.dashscope_base_url = data.dashscope_base_url
    row.reasoning_effort = data.reasoning_effort
    row.timeout_seconds = data.timeout_seconds
    # 四项生成参数整条覆盖：留空 = 回到代码默认，不做"空则保留原值"的兼容，
    # 否则管理员永远没法把设过的温度改回默认。
    row.temperature = data.temperature
    row.top_p = data.top_p
    row.max_output_tokens = data.max_output_tokens
    # 提示词按"空字符串 = 清空，回退内置"处理。
    row.system_prompt = (data.system_prompt or "").strip() or None
    row.context_window = data.context_window
    row.is_active = data.is_active
    if data.api_key:
        row.api_key_encrypted = encrypt_api_key(data.api_key)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def list_configs(db: AsyncSession) -> list[ProviderConfigView]:
    """返回全部能力的配置视图（未配置的能力给占位项，key脱敏）。"""

    rows = (await db.scalars(select(AIProviderConfig))).all()
    by_capability = {row.capability: row for row in rows}

    result: list[ProviderConfigView] = []
    for capability in VALID_CAPABILITIES:
        row = by_capability.get(capability)
        if row is None:
            result.append(
                ProviderConfigView(
                    capability=capability,
                    allowed_providers=list(get_allowed_providers(capability)),
                    provider="",
                    model="",
                    base_url="",
                    dashscope_base_url=None,
                    api_key_masked=None,
                    has_key=False,
                    reasoning_effort=None,
                    timeout_seconds=None,
                    is_active=False,
                )
            )
            continue
        masked, has_key = _mask_api_key(row.api_key_encrypted)
        result.append(
            ProviderConfigView(
                capability=row.capability,
                allowed_providers=list(get_allowed_providers(row.capability)),
                provider=row.provider,
                model=row.model,
                base_url=row.base_url,
                dashscope_base_url=row.dashscope_base_url,
                api_key_masked=masked,
                has_key=has_key,
                reasoning_effort=row.reasoning_effort,
                timeout_seconds=row.timeout_seconds,
                temperature=row.temperature,
                top_p=row.top_p,
                max_output_tokens=row.max_output_tokens,
                system_prompt=row.system_prompt,
                context_window=row.context_window,
                is_active=row.is_active,
            )
        )
    return result

"""AI助手接口使用的请求与响应Schema。

调用位置：
- ``ai_router.chat()`` 使用 ``ChatRequest`` 接收并校验前端JSON；
- ``ai_services.chat()`` 返回 ``ChatResponse``；
- ``ApiResponse.success()`` 最后把 ``ChatResponse`` 序列化到响应的 ``data`` 字段。

本文件只定义数据形状和输入校验，不调用百炼，也不处理HTTP异常。
"""

# BaseModel让普通Python类获得Pydantic校验和JSON序列化能力；
# Field声明长度、默认值等字段约束；field_validator用于空白字符串校验。
from datetime import date, datetime, time

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """前端本轮发送给AI助手的请求JSON。"""

    # message对应请求JSON中的"message"。
    # 前端只提交本轮问题，不需要重复上传以前的完整messages历史；
    # min_length拦截空字符串，max_length限制单次输入规模和不可控费用。
    message: str = Field(min_length=1, max_length=4_000)

    # 会话ID：前端首次提问不传（None），后端创建新会话并返回；后续轮次带上前端
    # 收到的session_id，后端把本轮消息追加进该会话，实现多轮连续。
    # MiniMax的Responses API不支持previous_response_id（会被忽略），因此用会话表
    # 维护历史，不再依赖服务端上下文。
    session_id: int | None = Field(default=None)

    # 装饰器告诉Pydantic：创建ChatRequest时，要用下面的方法继续校验message字段。
    @field_validator("message")
    # Pydantic字段校验器按类方法调用，不依赖某个已经创建完成的对象。
    @classmethod
    def normalize_message(cls, value: str) -> str:
        """去掉首尾空格，并拒绝只由空白组成的消息。"""

        # ``strip()``把"  怎么预约？  "规范化为"怎么预约？"。
        value = value.strip()

        # Field(min_length=1)只能拦截真正的空字符串；"   "原本仍有长度。
        # strip后再次判断，才能拒绝只包含空格、换行或制表符的输入。
        if not value:
            # ValueError会由Pydantic收集，最终进入项目的422全局校验异常处理器。
            raise ValueError("消息内容不能为空")

        # 校验器必须返回规范化后的值；后续Service拿到的data.message就是这个结果。
        return value


class ChatSource(BaseModel):
    """本轮回答实际使用的知识库来源摘要。"""

    # Chunk ID用于请求受保护的来源图片，不向前端暴露服务器磁盘路径。
    chunk_id: int

    # 文档ID可供后台详情页或以后制作“查看原文”接口使用。
    document_id: int

    # 原始文件名适合直接展示，例如“人工智能实验室安全规范.pdf”。
    file_name: str

    # PDF/DOCX解析结果可能有页码；其他格式没有时返回None。
    page_number: int | None = None

    # Markdown标题路径或解析阶段保存的章节标题。
    heading_path: str | None = None

    # text表示纯文本Chunk，image表示该来源还带有已入库图片。
    modality: str

    # 图片来源使用后端鉴权接口；纯文本来源为None。
    image_url: str | None = None

    # 这是余弦距离，不是准确率或百分比；越小表示向量越接近。
    distance: float


class UsageInfo(BaseModel):
    """本轮请求的token用量，来自模型响应的usage字段。"""

    # 输入token：本轮问题+系统提示+检索资料+历史上下文合计。
    input_tokens: int = 0

    # 输出token：模型本轮生成的回答（含思考Token，若模型支持思考）。
    output_tokens: int = 0

    # 输入+输出合计。
    total_tokens: int = 0


class PendingReservationAction(BaseModel):
    """聊天响应中给前端展示的预约确认卡片。"""

    action_id: int
    lab_id: int
    lab_name: str
    equipment_id: int | None = None
    equipment_name: str | None = None
    date: date
    start_time: time
    end_time: time
    remark: str | None = None
    expires_at: datetime


class ConfirmedReservationAction(BaseModel):
    """确认接口返回的幂等结果。"""

    action_id: int
    reservation_id: int
    already_confirmed: bool = False


class SessionPendingAction(PendingReservationAction):
    """历史会话里恢复出来的草稿：比实时响应多一个状态。

    实时响应里的 pending_action 只在当轮有效，用户刷新页面或从会话列表切回来时
    拿不到 action_id 就没法确认，所以详情接口要能把还存在的草稿连状态一起回给前端。
    """

    # pending=还能确认；completed=已生成预约；expired=超时；cancelled 不返回给前端。
    status: str
    reservation_id: int | None = None


class ChatResponse(BaseModel):
    """Service返回模型回答、会话ID和知识来源。"""

    message: str

    # 会话ID：前端保存后，后续轮次作为session_id回传以延续对话。
    session_id: int

    # 实际使用的模型ID，前端据此展示“当前用的哪个模型”。
    model: str

    # 本轮token用量；模型或兼容层未返回usage时为None，前端应容错处理。
    usage: UsageInfo | None = None

    # 没检索到可用文档时返回空列表，不返回None，前端处理更稳定。
    sources: list[ChatSource] = Field(default_factory=list)
    # 本轮模型实际请求过的工具名称；没有调用工具时为空列表。
    used_tools: list[str] = Field(default_factory=list)
    pending_action: PendingReservationAction | None = None
    # 本轮从收到请求到落库的总耗时（毫秒），前端显示“用时 x.x 秒”。
    duration_ms: int | None = None


class ChatMessageItem(BaseModel):
    """会话历史中的一条消息。"""

    role: str
    content: str


class ChatSessionSummary(BaseModel):
    """会话列表页的一项摘要。"""

    id: int
    title: str
    updated_at: datetime


class ChatSessionDetail(BaseModel):
    """会话详情：标题与完整消息历史。"""

    id: int
    title: str
    messages: list[ChatMessageItem]
    # 本会话里还没作废的预约草稿，供前端恢复确认卡片；没有则为空列表。
    pending_actions: list[SessionPendingAction] = Field(default_factory=list)


class SessionTitleRequest(BaseModel):
    """用户自定义会话标题。

    max_length 与 ``ChatSession.title`` 的 String(100) 对齐；自动标题只截首句前
    30 字，手动改允许更长，但不超过列宽，避免数据库报错冒成 500。
    """

    title: str = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """去掉首尾空白；纯空白标题视为空标题直接拒绝。"""

        value = value.strip()
        if not value:
            raise ValueError("会话标题不能为空")
        return value


class ModelOption(BaseModel):
    """前端模型选择器使用的单项模型信息。"""

    # 模型ID；配置页保存到对应能力的数据库配置中。
    id: str

    # 给人看的模型名，例如“MiniMax M3”。
    name: str

    # 上下文窗口大小（token数），前端用于展示“已用X/窗口Y”的进度。
    context_window: int

    # 是否支持图片输入；前端据此决定以图检索按钮是否可用。
    vision: bool

    # 是否支持思考层级参数；前端据此决定是否显示思考层级选择器。
    reasoning: bool

    # 是否为当前已配置模型；供应商候选查询阶段通常为False。
    is_default: bool


class ModelListResponse(BaseModel):
    """GET /api/ai/models 返回的可用模型列表。"""

    models: list[ModelOption]
    # 未配置 chat 能力时不存在默认模型。
    default_model: str | None


class ProviderModelsRequest(BaseModel):
    """管理员查询某供应商可用模型时提交的鉴权信息。

    该接口只用于"填key后查询/验证模型列表"，key仅在本次请求内存中使用，
    不落库、不写日志；真正保存配置走配置接口（加密存储）。

    ``provider`` 在 Pydantic 层只做长度校验，具体的供应商合法性由 Router
    对照 ``ai_provider_services.VALID_PROVIDERS`` 二次校验并抛出 400，
    避免注册表外的未知 provider 直接变成 500。
    """

    provider: str = Field(min_length=1, max_length=30)
    base_url: str = Field(min_length=1, max_length=300)
    api_key: str = Field(min_length=1, max_length=500)
    # 能力筛选：可选；指定后只返回能用作该能力的模型。
    # 当前合法值同 ai_provider_services.VALID_CAPABILITIES。
    capability: str | None = Field(default=None, max_length=30)


class ProviderConfigUpsertRequest(BaseModel):
    """管理员保存某个能力的供应商配置。

    api_key 为空字符串或 None 表示不更新密钥（保留原值）；非空则加密覆盖。
    dashscope_base_url 为空字符串表示显式清空；None 表示不修改。
    """

    provider: str = Field(min_length=1, max_length=30)
    model: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=300)
    dashscope_base_url: str | None = Field(default=None, max_length=300)
    api_key: str | None = Field(default=None, max_length=500)
    reasoning_effort: str | None = Field(default=None, max_length=20)
    timeout_seconds: float | None = Field(default=None, gt=0, le=300)
    # 以下四项留空表示沿用代码默认；给了就覆盖该能力的生成行为。
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_output_tokens: int | None = Field(default=None, ge=1, le=131_072)
    system_prompt: str | None = Field(default=None, max_length=20_000)
    # 模型上下文窗口，配置页选模型时自动带上；留空则由后端查 MODEL_CATALOG。
    context_window: int | None = Field(default=None, ge=0, le=10_000_000)
    is_active: bool = True


class ProviderConfigView(BaseModel):
    """配置列表项；api_key 脱敏展示，不回传明文。"""

    capability: str
    # 由后端返回能力与供应商的兼容矩阵，前端只负责展示，不能自己定义安全规则。
    allowed_providers: list[str]
    provider: str
    model: str
    base_url: str
    dashscope_base_url: str | None
    api_key_masked: str | None
    has_key: bool
    reasoning_effort: str | None
    timeout_seconds: float | None
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    system_prompt: str | None = None
    context_window: int | None = None
    is_active: bool

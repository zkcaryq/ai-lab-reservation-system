"""应用配置：只负责读取与校验环境变量，不建立数据库连接。"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """从系统环境变量和项目根目录的 .env 读取配置。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        hide_input_in_errors=True,
        frozen=True,
    )

    APP_NAME: str = Field(default="FastAPI Backend", min_length=1)
    APP_ENV: Literal["development", "testing", "production"] = "development"
    HOST: str = "127.0.0.1"
    PORT: int = Field(default=8000, ge=1, le=65535)
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # 浏览器只允许这些前端“源”跨域访问后端。
    # 源由“协议 + 主机 + 端口”组成，末尾不要填写路径或斜杠。
    # 在 .env 中覆盖时必须使用 JSON 数组，例如：
    # CORS_ORIGINS=["http://localhost:5173","http://192.168.1.10:5173"]
    CORS_ORIGINS: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )

    # 当前项目把 JWT 放在 Authorization 请求头中，并不依赖跨站 Cookie，
    # 因此默认关闭凭据模式。以后改成 HttpOnly Cookie 登录时再明确开启。
    CORS_ALLOW_CREDENTIALS: bool = False

    DB_HOST: str = Field(min_length=1)
    DB_PORT: int = Field(default=5432, ge=1, le=65535)
    DB_NAME: str = Field(min_length=1)
    DB_USER: str = Field(min_length=1)
    DB_PASSWORD: SecretStr

    # 开发环境可留空并回退到运行账号；生产环境可配置单独的 DDL 账号。
    MIGRATION_DB_USER: str | None = None
    MIGRATION_DB_PASSWORD: SecretStr | None = None

    DB_SCHEMA: str = Field(pattern=r"^[a-z_][a-z0-9_]{0,62}$")
    DB_SSLMODE: Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"] = (
        "prefer"
    )
    DB_SSLROOTCERT: Path | None = None
    DB_CONNECT_TIMEOUT: int = Field(default=5, ge=1, le=60)
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=5, ge=0, le=100)
    DB_POOL_TIMEOUT: float = Field(default=10, gt=0, le=120)
    DB_STATEMENT_TIMEOUT_MS: int = Field(default=30_000, ge=1_000, le=600_000)
    DB_IDLE_IN_TX_TIMEOUT_MS: int = Field(default=60_000, ge=1_000, le=600_000)
    HEALTH_TIMEOUT: float = Field(default=5, gt=0, le=60)

    # 待审核预约超过该分钟数仍未被管理员处理时，由后台任务自动通过。
    RESERVATION_AUTO_APPROVE_MINUTES: int = Field(default=15, ge=1, le=24 * 60)

    # 后台任务检查待审核预约的间隔。最低10秒，避免误配置造成高频数据库请求。
    RESERVATION_REVIEW_SCAN_SECONDS: int = Field(default=60, ge=10, le=3_600)

    # 整个HTTP请求体上限默认6 MiB：为5 MiB文件和multipart协议开销留出空间。
    MAX_REQUEST_BODY_BYTES: int = Field(
        default=6 * 1024 * 1024,
        ge=1_024,
        le=33_554_432,
    )
    SHUTDOWN_TIMEOUT: float = Field(default=10, gt=0, le=60)

    # JWT签名密钥属于敏感配置，因此使用SecretStr，避免它在普通日志和报错中被直接显示。
    # 真实值只应写在本地.env或部署平台的Secret中，不能提交到Git。
    JWT_SECRET_KEY: SecretStr

    # AI 供应商配置密钥（API Key）的加密密钥。建议与 JWT_SECRET_KEY 不同，
    # 否则轮换 JWT 密钥会导致数据库里所有 AI Key 无法解密。
    # 为空时回退到 JWT_SECRET_KEY（旧数据兼容），首次部署建议显式配置以隔离风险。
    AI_CONFIG_ENCRYPTION_KEY: SecretStr | None = None

    # 当前项目只允许服务端明确选择HS256，不能让客户端Token自行决定验签算法。
    JWT_ALGORITHM: Literal["HS256"] = "HS256"

    # Access Token默认48小时过期；gt和le同时限制配置必须大于0且最长不超过30天。
    JWT_EXPIRE_HOURS: int = Field(default=48, gt=0, le=24 * 30)
    # 上传文件保存目录；PROJECT_ROOT是backend目录，所以默认路径是backend/uploads。
    # 生产环境可以通过.env的UPLOAD_DIR覆盖为持久化磁盘的绝对路径。
    UPLOAD_DIR: Path = PROJECT_ROOT / "uploads"

    # 单个上传文件最大5 MiB。
    MAX_UPLOAD_FILE_BYTES: int = Field(
        # default只在.env没有提供MAX_UPLOAD_FILE_BYTES时使用。
        default=5 * 1024 * 1024,
        # 至少允许1 KiB，避免误配置成0或负数。
        ge=1024,
        # 当前项目上限封顶32 MiB，防止配置错误导致超大文件进入应用。
        le=32 * 1024 * 1024,
    )

    # 第一版只允许公开头像图片；.env覆盖时必须使用JSON数组。
    ALLOWED_UPLOAD_EXTENSIONS: tuple[str, ...] = (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    )
    # 聊天回答的输出Token上限。对Qwen3.8系列，这个上限同时包含思考与回复：
    # 曾用1024导致“列出实验室+依据文档名”的长回答被拦腰截断（正文停在“依据：《0”），
    # 因此聊天上限必须明显高于图片描述；实际计费按生成量，提高上限不增加固定成本。
    BAILIAN_CHAT_MAX_OUTPUT_TOKENS: int = Field(default=4_096, ge=256, le=65_536)

    # 本项目统一使用1024维。环境变量最初是字符串，因此这里声明为int，
    # 让Pydantic先把"1024"转换成整数；ge和le都写1024，防止配置与
    # 数据库中的vector(1024)列不一致。
    BAILIAN_EMBEDDING_DIMENSION: int = Field(
        default=1024,
        ge=1024,
        le=1024,
    )

    # 原文件、提取图片和临时解压目录都放在私有目录，不挂载到/uploads。
    # .env允许写相对路径；下面的storage_directory_path校验器会把它转换成
    # 相对于backend根目录的绝对路径，避免启动目录变化导致文件保存到其他位置。
    KNOWLEDGE_STORAGE_DIR: Path = PROJECT_ROOT / "storage" / "knowledge"

    # 知识文档允许比头像大，但第一版封顶20MiB。
    MAX_KNOWLEDGE_FILE_BYTES: int = Field(
        default=20 * 1024 * 1024,
        ge=1024,
        le=100 * 1024 * 1024,
    )

    # AI以图检索只接收普通图片，不需要放宽到完整知识文档的20MiB上限。
    MAX_AI_QUERY_IMAGE_BYTES: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
        le=20 * 1024 * 1024,
    )

    # ZIP只用于Markdown和配套媒体组成的文档包，不接受任意程序压缩包。
    ALLOWED_KNOWLEDGE_EXTENSIONS: tuple[str, ...] = (
        ".docx",
        ".pdf",
        ".xlsx",
        ".md",
        ".zip",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    )

    # Worker无任务时的轮询间隔；不能写成0形成空转。
    KNOWLEDGE_WORKER_SCAN_SECONDS: float = Field(default=2, ge=0.5, le=60)
    # 本地开发默认由Web进程内启动；生产多进程部署时可设为false，改用独立Worker命令。
    KNOWLEDGE_WORKER_ENABLED: bool = True

    # 单份文档从解析到向量入库的总时限。超时后任务会被标记为failed，
    # 防止外部模型或异常文档让processing状态永久卡住。
    KNOWLEDGE_TASK_TIMEOUT_SECONDS: float = Field(default=1800, ge=60, le=7200)

    # Worker空闲时定期重新检查孤儿任务的间隔。
    # 孤儿任务指进程中断（崩溃、强杀、快速重启）遗留的processing记录：
    # 启动时会检查一次，但“刚中断、还没超过任务时限”的任务不会被恢复；
    # 运行期间按此间隔再次检查，时限一到就放回队列，不再依赖下一次重启。
    KNOWLEDGE_STALE_RECHECK_SECONDS: float = Field(default=60, ge=10, le=3_600)

    # 以下限制约束“文件解包和解析后的工作量”，与20MiB上传大小限制互补。
    # 一个体积不大的压缩文档仍可能包含大量页面、图片或文字，因此必须分别限制。
    KNOWLEDGE_MAX_PAGES: int = Field(default=200, ge=1, le=1000)
    KNOWLEDGE_MAX_IMAGES: int = Field(default=100, ge=0, le=1000)
    KNOWLEDGE_MAX_CHUNKS: int = Field(default=2000, ge=1, le=10000)
    KNOWLEDGE_MAX_TEXT_CHARS: int = Field(default=2_000_000, ge=1000, le=10_000_000)

    # 向量召回先取较多候选，再由可选的排序模型精排成最终Top K。
    RAG_CANDIDATE_LIMIT: int = Field(default=20, ge=5, le=100)

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def sufficiently_long_jwt_secret(cls, value: SecretStr) -> SecretStr:
        """拒绝过短的JWT签名密钥。"""

        # SecretStr不会通过str(value)返回原文，校验长度时必须显式读取真实值。
        # 这里检查的是字符数，不等于完整的密码学强度；密钥仍应由安全随机数生成器生成。
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET_KEY 至少需要 32 个字符")

        # Pydantic字段校验器必须返回通过校验的值，才能继续创建Settings对象。
        return value

    @field_validator("AI_CONFIG_ENCRYPTION_KEY")
    @classmethod
    def sufficiently_long_ai_encryption_key(cls, value: SecretStr | None) -> SecretStr | None:
        """校验 AI 配置加密密钥的最低长度。

        未配置时返回 None，调用方应回退到 JWT_SECRET_KEY 以兼容旧数据。
        """

        if value is None:
            return None
        if len(value.get_secret_value()) < 32:
            raise ValueError("AI_CONFIG_ENCRYPTION_KEY 至少需要 32 个字符")
        return value

    @field_validator("DB_PASSWORD")
    @classmethod
    def nonempty_password(cls, value: SecretStr) -> SecretStr:
        """拒绝空数据库密码，避免应用带错误凭据启动。"""

        if not value.get_secret_value():
            raise ValueError("DB_PASSWORD 不能为空")
        return value

    @field_validator("DB_SCHEMA")
    @classmethod
    def application_schema(cls, value: str) -> str:
        """禁止把业务表放进 PostgreSQL 保留 Schema。"""

        if value.startswith("pg_") or value == "information_schema":
            raise ValueError("不能使用 PostgreSQL 系统 Schema")
        return value

    @field_validator("DB_HOST", "DB_NAME", "DB_USER", "APP_NAME", "HOST")
    @classmethod
    def nonblank_value(cls, value: str) -> str:
        """拒绝仅由空白字符构成的关键字符串配置。"""

        if not value.strip():
            raise ValueError("配置不能仅包含空白")
        return value

    @field_validator("UPLOAD_DIR", "KNOWLEDGE_STORAGE_DIR")
    @classmethod
    def storage_directory_path(cls, value: Path) -> Path:
        """把.env中的相对存储目录固定到backend根目录。"""

        # Path.is_absolute()同时适配Windows盘符路径和Linux根路径。
        # 生产环境如果配置/srv/...会原样保留；本地的storage/...会落到backend下。
        if value.is_absolute():
            return value
        return PROJECT_ROOT / value

    @model_validator(mode="after")
    def validate_cross_field_settings(self) -> "Settings":
        """验证多个配置项之间必须共同满足的启动约束。"""

        # 浏览器规范不允许“任意来源”与凭据模式组合使用，启动时直接拒绝错误配置。
        if self.CORS_ALLOW_CREDENTIALS and "*" in self.CORS_ORIGINS:
            raise ValueError('CORS_ALLOW_CREDENTIALS=true 时不能使用 CORS_ORIGINS=["*"]')

        # BodySizeLimitMiddleware先检查整个multipart请求，再轮到上传Router检查文件本身。
        # 因此请求体上限必须更大，否则合法大小的文件也会在进入Router前被413拦截。
        largest_upload = max(
            self.MAX_UPLOAD_FILE_BYTES,
            self.MAX_KNOWLEDGE_FILE_BYTES,
            self.MAX_AI_QUERY_IMAGE_BYTES,
        )
        if largest_upload >= self.MAX_REQUEST_BODY_BYTES:
            raise ValueError(
                "MAX_REQUEST_BODY_BYTES必须大于所有单文件上传上限，为multipart请求头和边界保留空间"
            )

        has_user = self.MIGRATION_DB_USER is not None
        has_password = self.MIGRATION_DB_PASSWORD is not None
        if has_user != has_password:
            raise ValueError("MIGRATION_DB_USER 和 MIGRATION_DB_PASSWORD 必须同时设置")
        return self

    @property
    def database_url(self) -> URL:
        """运行时连接；URL.create 会正确转义密码中的特殊字符。"""

        return URL.create(
            "postgresql+psycopg",
            username=self.DB_USER,
            password=self.DB_PASSWORD.get_secret_value(),
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        )

    @property
    def migration_database_url(self) -> URL:
        """Alembic 连接；没有单独配置时回退到运行时账号。"""

        user = self.MIGRATION_DB_USER or self.DB_USER
        password = self.MIGRATION_DB_PASSWORD or self.DB_PASSWORD
        return URL.create(
            "postgresql+psycopg",
            username=user,
            password=password.get_secret_value(),
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        )

    @property
    def connect_args(self) -> dict[str, str | int]:
        """传给 psycopg 的连接、SSL、时区和数据库级超时参数。"""

        args: dict[str, str | int] = {
            "connect_timeout": self.DB_CONNECT_TIMEOUT,
            "sslmode": self.DB_SSLMODE,
            "options": (
                "-csearch_path=pg_catalog,public "
                "-ctimezone=UTC "
                f"-cstatement_timeout={self.DB_STATEMENT_TIMEOUT_MS} "
                f"-cidle_in_transaction_session_timeout={self.DB_IDLE_IN_TX_TIMEOUT_MS}"
            ),
        }
        if self.DB_SSLROOTCERT is not None:
            args["sslrootcert"] = str(self.DB_SSLROOTCERT)
        return args


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """同一进程只读取并校验一次配置。"""

    return Settings()

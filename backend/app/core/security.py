"""认证安全基础能力：Argon2id密码哈希与JWT访问令牌。

职责边界：本模块属于core层，只提供与FastAPI无关的纯安全工具函数；
它自己不导入FastAPI、不访问数据库、也不感知HTTP。

调用关系速览（谁调用本模块的哪个函数）：

- ``services/auth_router.py``
  - 登录时调用 ``verify_password()`` 核对密码；
  - 验证成功后调用 ``password_needs_rehash()`` 判断是否要升级旧哈希；
  - 需要升级时调用 ``hash_password()`` 用当前参数重新哈希；
  - 将来出现"创建用户/修改密码"功能时也会调用 ``hash_password()``。
- ``api/routes/auth_router.py``
  - 登录成功后调用 ``create_access_token()`` 签发Token。
- ``api/dependencies.py``（鉴权依赖，教程06后续小节实现）
  - 调用 ``decode_access_token()`` 解析请求携带的Token。
"""

# datetime负责生成带UTC时区的签发时间和过期时间；timedelta负责计算有效期。
from datetime import UTC, datetime, timedelta
from typing import Any

# PyJWT提供JWT的编码和解码能力。
import jwt

# PasswordHasher是argon2-cffi推荐的高层密码哈希接口。
from argon2 import PasswordHasher

# InvalidHashError表示传入的字符串不是合法Argon2哈希；
# VerificationError是验证过程失败的基类（密码不匹配就属于它）。
from argon2.exceptions import InvalidHashError, VerificationError

# Type枚举来自底层绑定模块，用于显式选择Argon2的id变体。
from argon2.low_level import Type

from app.core.settings import get_settings

# get_settings()内部有lru_cache：本进程只有第一次调用会真正读取.env并校验，
# 之后所有模块拿到的都是同一个Settings对象。
# 写在模块顶层意味着"导入本模块就检查配置"：如果.env缺少JWT_SECRET_KEY，
# 进程会在导入阶段立即启动失败，而不是等到第一个用户登录时才报错。
# 这种"尽早失败"（fail fast）能把配置问题暴露在最前面。
settings = get_settings()

# 显式记录本项目使用的Argon2id参数，而不是隐式依赖第三方库的默认值。
# 这些数值与当前argon2-cffi 25.1的默认参数一致，也对应RFC 9106的
# "第二推荐参数"（第一推荐需要2 GiB内存，对个人和中小项目过重）：
# - time_cost：迭代次数t；越大越消耗CPU；
# - memory_cost：单次哈希占用的内存m，单位KiB；65536 KiB = 64 MiB；
# - parallelism：并行度p，即把内存分成几路同时计算；
# - hash_len：最终哈希摘要的字节长度；
# - salt_len：随机salt的字节长度。
# Argon2与bcrypt相比的关键优势：它同时消耗CPU和内存，提高任一参数都会
# 让暴力破解按数量级变贵，因此参数可以随硬件升级逐步提高。
# 将来经过压测提高这里的任一参数后，数据库中的旧哈希就会被
# password_needs_rehash()识别为"需要升级"，登录成功后自动重算。
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65_536
ARGON2_PARALLELISM = 4
ARGON2_HASH_LENGTH = 32
ARGON2_SALT_LENGTH = 16

# PasswordHasher在每次hash()时自动生成随机salt，并把算法类型、版本、
# 参数、salt和摘要一起编码进最终字符串，例如：
#   $argon2id$v=19$m=65536,t=3,p=4$<salt>$<摘要>
# 因此数据库只需保存这一条完整字符串，不需要单独的salt字段；verify()
# 也因此能从字符串中读回"当时"的参数去验证旧哈希。
# 实例本身没有可变内部状态（hash/verify只读取这里的配置），
# 多个请求并发调用同一个实例是安全的。
# type=Type.ID显式选择Argon2id变体：它同时具备抗侧信道和
# 抗时间-内存折中攻击的性质，是当前业界推荐的默认选择。
password_hasher = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST,
    parallelism=ARGON2_PARALLELISM,
    hash_len=ARGON2_HASH_LENGTH,
    salt_len=ARGON2_SALT_LENGTH,
    type=Type.ID,
)


def hash_password(password: str) -> str:
    """使用当前Argon2id参数为明文密码生成不可逆哈希。

    Args:
        password: 用户提交的明文密码。

    Returns:
        形如 ``$argon2id$v=19$m=65536,t=3,p=4$...`` 的完整哈希字符串，
        可直接保存到 ``users.password`` 列。
    """

    # hash()每次调用都会生成新的随机salt；即使明文相同，两次结果也不同，
    # 所以验证密码不能"重新哈希再比较字符串"，必须走verify_password()。
    # Argon2没有bcrypt的72字节输入上限，因此这里不需要检查密码长度；
    # 请求体大小限制（MAX_REQUEST_BODY_BYTES）已在更外层兜底。
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """验证明文密码是否匹配数据库中保存的Argon2哈希。

    Args:
        password: 用户本次登录输入的明文。
        password_hash: 数据库 ``users.password`` 列中的哈希字符串。

    Returns:
        匹配返回True；密码错误或哈希本身不合法时返回False。
    """

    try:
        # verify()的参数顺序固定是"数据库哈希在前，用户输入的明文在后"。
        # 它会从password_hash自身解析出签发时的算法类型和t/m/p参数，
        # 因此即使将来提高了上面的常量，旧参数生成的哈希仍然能验证通过。
        # 密码匹配时返回True；密码不匹配时抛VerifyMismatchError。
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        # 这两个异常必须同时捕获，因为它们的继承体系并不相通（已实测确认）：
        # - VerificationError：继承自argon2.exceptions.Argon2Error，
        #   覆盖"密码不匹配"等验证失败；
        # - InvalidHashError：继承自Python内建的ValueError，
        #   表示字符串根本不是合法Argon2哈希（例如数据库里仍是明文密码）。
        # 统一返回False后，登录接口只呈现"账号或密码错误"，
        # 不会把argon2内部异常变成HTTP 500暴露给客户端。
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """判断已有哈希是否需要按当前参数重新计算（升级）。

    Args:
        password_hash: 数据库中保存的完整哈希字符串。

    Returns:
        哈希内记录的参数与当前 ``password_hasher`` 配置不一致时返回True。
    """

    # 只能在verify_password()验证成功后调用，原因有二：
    # 1. 只有合法哈希才能被解析出参数，对明文或损坏字符串会抛InvalidHashError；
    # 2. 重新哈希需要明文密码，而服务器只有在用户登录的那一刻
    #    才同时拥有明文和旧哈希，其他任何时机都无法完成升级。
    # check_needs_rehash()只做"字符串里的参数"与"当前配置"的对比，
    # 不访问数据库、不做任何重计算，因此开销可以忽略。
    # 调用方（services/auth_router.py）发现返回True后，应使用本次登录的明文密码
    # 调用hash_password()重新生成哈希并提交数据库。
    return password_hasher.check_needs_rehash(password_hash)


def create_access_token(user_id: int) -> str:
    """创建包含用户身份、签发时间和过期时间的JWT Access Token。

    Args:
        user_id: 数据库 ``users.id`` 主键。

    Returns:
        签名后的JWT字符串，由登录Router放进响应data.token返回给客户端。
    """

    # 始终使用带时区的UTC时间，避免服务器位于不同时区时产生歧义。
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=settings.JWT_EXPIRE_HOURS)

    # 三个字段都使用JWT标准（RFC 7519）定义的"注册声明"名称：
    # - sub（subject，主题）：这个Token代表谁；规范要求它是字符串，
    #   所以把数据库整数主键转成str，解码方拿到后再自己转回int；
    # - iat（issued at，签发时间）；
    # - exp（expiration，过期时间）：jwt.decode()会自动校验exp，
    #   过期时抛ExpiredSignatureError，不需要调用方自己比较时间。
    # PyJWT会把datetime对象自动转换成Unix时间戳整数再写入Token。
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expires_at,
    }

    # HS256是对称签名：签发和验证使用同一份密钥，所以密钥必须严格保密
    # （对照：RS256是非对称签名，签发用私钥、验证用公钥）。
    # SecretStr普通打印只显示掩码；真正签名时才用get_secret_value()取出明文。
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """校验JWT签名和时间声明，并返回通过验证的载荷。

    Args:
        token: 从 ``Authorization: Bearer ...`` 中提取的Token字符串。

    Returns:
        通过验证的载荷字典；其中 ``sub`` 是字符串， ``iat``/``exp`` 是
        Unix时间戳整数。注意此函数只验Token，不查数据库。

    Raises:
        jwt.ExpiredSignatureError: Token已过期。
        jwt.InvalidSignatureError: 签名不匹配（Token被篡改或密钥不符）。
        jwt.InvalidTokenError: 其他Token格式或声明问题
            （以上三个异常都继承自它，由鉴权依赖统一转成HTTP 401）。
    """

    # algorithms必须由服务端明确指定白名单，不能相信Token头部自己声明的算法。
    # 如果不限制，攻击者可能把Token头的alg改成别的值来绕过校验
    # （即"算法混淆攻击"）。这里固定只接受服务端配置的HS256。
    # 签名错误、Token过期或格式损坏时，PyJWT会抛出各自明确的异常类型，
    # 之后由鉴权依赖捕获并转换成HTTP 401，而不是让请求变成500。
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )

"""登录用户的公开图片上传接口。

请求调用链：浏览器multipart请求 -> BodySizeLimitMiddleware -> CurrentUser鉴权
-> 本文件的upload_file() -> 分块写入backend/uploads -> 返回公开相对URL。

这里只允许公开头像类图片。后缀白名单不能验证真实文件内容，私有文档也不能
通过本模块的StaticFiles公开方案保存。
"""

# uuid用于生成无法由用户控制、几乎不会重复的磁盘文件名。
import uuid

# Path负责读取后缀和拼接磁盘路径；PurePosixPath用于安全提取原文件名最后一段。
from pathlib import Path, PurePosixPath

# Annotated给UploadFile附加File元信息；BinaryIO描述同步二进制文件流。
from typing import Annotated, BinaryIO

# APIRouter声明子路由；File声明multipart文件字段；UploadFile提供临时文件对象。
from fastapi import APIRouter, File, UploadFile

# CurrentUser要求请求携带有效Bearer Token，并确保用户仍存在且状态正常。
from app.api.dependencies import CurrentUser

# BusinessException用于可预期的400、413、415，由全局处理器生成统一JSON。
from app.core.errors import BusinessException

# get_settings返回缓存的Settings，读取上传目录、大小上限和允许后缀。
from app.core.settings import get_settings

# ApiResponse统一成功响应的code、message和data外形。
from app.schemas.apiresponse import ApiResponse
from app.schemas.file_schemas import FileUploadResponse

# 所有本模块路由都会自动带/files前缀；上层再加/api，最终为/api/files。
router = APIRouter(prefix="/files", tags=["文件管理"])

# get_settings()有lru_cache，同一进程内不会反复读取.env。
settings = get_settings()

# 每次读取1 MiB，避免把完整文件一次性读进内存。
COPY_CHUNK_BYTES = 1024 * 1024


class _UploadTooLarge(Exception):
    """内部控制信号：实际写入字节超过单文件上限。

    下划线前缀表示它只供本模块内部使用；Router会把它转换成HTTP 413，
    不会让内部异常类型直接暴露给客户端。
    """


def _copy_limited(
    source: BinaryIO,
    destination: Path,
    *,
    max_bytes: int,
) -> int:
    """分块复制文件并返回实际字节数；失败时删除半成品。

    Args:
        source: UploadFile.file提供的同步二进制读取流。
        destination: 使用UUID生成的最终磁盘路径。
        max_bytes: 单个文件允许写入的最大字节数。

    Returns:
        实际成功写入磁盘的总字节数。
    """

    # total累计真实读取到的字节，不能只依赖请求声明或file.size。
    total = 0

    # 复制、大小检查或磁盘写入都可能失败，统一保证半成品被清理。
    try:
        # xb表示“新建并写入”；极小概率发生同名时不会覆盖已有文件。
        with destination.open("xb") as target:
            while chunk := source.read(COPY_CHUNK_BYTES):
                # len(chunk)是本轮真实读取的字节数，累加后得到实际文件大小。
                total += len(chunk)

                # 在写入当前超限块之前中断，因此磁盘不会继续增长。
                if total > max_bytes:
                    raise _UploadTooLarge

                # 当前块仍在上限内，才写入目标文件。
                target.write(chunk)
    except Exception:
        # 超限或磁盘异常都不能留下不完整文件。
        destination.unlink(missing_ok=True)

        # 原样重新抛出：超限由Router转413，其他磁盘错误由全局中间件转500并记录日志。
        raise

    # 完整复制结束后，把真实大小交给Router写入响应data。
    return total


@router.post("/upload")
# 同步def会由FastAPI放进线程池，避免本地open/read/write直接阻塞主事件循环。
def upload_file(
    # File()告诉FastAPI从multipart/form-data中读取名为file的文件字段。
    file: Annotated[UploadFile, File()],
    # 声明CurrentUser会执行完整JWT鉴权；下划线表示函数只需要鉴权结果而不读取用户字段。
    _current_user: CurrentUser,
) -> ApiResponse:
    """保存一张公开图片，并返回可访问的相对URL。

    该接口不会修改User.avatar字段；本章只完成“上传并获得URL”。
    以后更新头像资料时，再由对应用户接口把URL写入数据库。
    """

    # 某些异常客户端可能提交空filename；没有名称时无法取得后缀。
    if not file.filename:
        raise BusinessException(
            # 这是请求内容问题，可以安全提示客户端。
            message="文件名不能为空",
            # HTTP 400表示请求缺少可用文件名。
            status_code=400,
        )

    # 浏览器可能提交C:\\fakepath\\avatar.jpg；先统一分隔符再只取最后一段。
    original_name = PurePosixPath(file.filename.replace("\\", "/")).name

    # suffix取得最后一个后缀；lower让.PNG与.png按照同一规则判断。
    extension = Path(original_name).suffix.lower()

    # 只允许Settings白名单中的公开图片后缀。
    if extension not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise BusinessException(
            # 没有后缀时显示“无后缀”，避免返回空提示。
            message=f"不支持的文件后缀：{extension or '无后缀'}",
            # HTTP 415表示服务器不支持这类上传媒体。
            status_code=415,
        )

    # size是multipart解析器统计的文件大小；有值时先快速拒绝。
    if file.size is not None and file.size > settings.MAX_UPLOAD_FILE_BYTES:
        raise BusinessException(
            # 字节数连续除以1024两次，转换为便于用户理解的MiB。
            message=(f"文件不能超过{settings.MAX_UPLOAD_FILE_BYTES // 1024 // 1024}MiB"),
            # HTTP 413表示请求内容超过服务器允许大小。
            status_code=413,
        )

    # 数据库和响应只保存随机磁盘名，不使用用户文件名作为磁盘路径。
    disk_name = f"{uuid.uuid4().hex}{extension}"

    # /运算符由pathlib安全拼接目录和文件名；disk_name不含用户提供的路径。
    save_path = settings.UPLOAD_DIR / disk_name

    # 实际复制仍可能发现size缺失或不准确，因此继续执行真实字节计数。
    try:
        # UploadFile.file是可读取的SpooledTemporaryFile；指针归零后开始复制。
        file.file.seek(0)
        actual_size = _copy_limited(
            file.file,
            save_path,
            max_bytes=settings.MAX_UPLOAD_FILE_BYTES,
        )
    except _UploadTooLarge:
        # 内部超限信号转换成与前置size检查相同的统一HTTP 413。
        raise BusinessException(
            message=(f"文件不能超过{settings.MAX_UPLOAD_FILE_BYTES // 1024 // 1024}MiB"),
            status_code=413,
        ) from None
    finally:
        # 本函数在线程池中运行，关闭底层临时文件是同步操作。
        file.file.close()

    # 文件已经完整落盘后才返回成功；磁盘错误不会执行到这里。
    return ApiResponse.success(
        # 保留项目当前的成功提示风格。
        message="上传成功!Ovo!",
        # data提供前端展示原名、保存URL以及后续写入avatar字段所需的信息。
        data=FileUploadResponse(
            original_name=original_name,
            disk_name=disk_name,
            size=actual_size,
            url=f"/uploads/{disk_name}",
        ),
    )

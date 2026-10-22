"""通用上传接口返回模型；上传校验和文件落盘由 Router/Service 完成。"""

from pydantic import BaseModel


class FileUploadResponse(BaseModel):
    """文件上传成功后返回给前端的数据。"""

    # 用户上传时的原始文件名，仅用于显示。
    original_name: str

    # 服务器使用UUID生成的实际保存名称。
    disk_name: str

    # 文件实际保存的字节数。
    size: int

    # 浏览器可以访问的静态资源相对URL。
    url: str

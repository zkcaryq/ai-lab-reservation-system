"""API 挂载入口。

模板本身不包含任何业务路由。新模块在这里
``api_router.include_router(xxx_router)``。
"""
# ↑ 模块 docstring：这是"业务 API 的汇总入口"，所有业务路由都在这里挂载。

# 从 FastAPI 导入 APIRouter（创建路由组用的类）。
from fastapi import APIRouter

from app.api.routes.auth import router as auth_router

# 当前模板把 API 版本号统一放在汇总路由上。
# 子路由只关心自己的业务前缀，避免每个模块都重复写 /api。
api_router = APIRouter(prefix="/api")
# ↑ 创建一个汇总路由，所有挂进来的业务接口都会带 /api 前缀。
#   比如挂一个 /students 路由，最终地址就是 /api/students。
#   当前项目按教程使用 /api；如果以后教程引入API版本管理，再统一调整为 /api/v1。

# auth_router 自带 /auth，因此最终路径为 /api/auth/login。
api_router.include_router(auth_router)

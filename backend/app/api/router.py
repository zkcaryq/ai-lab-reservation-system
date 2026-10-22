"""API 挂载入口。

模板本身不包含任何业务路由。新模块在这里
``api_router.include_router(xxx_router)``。
"""
# ↑ 模块 docstring：这是"业务 API 的汇总入口"，所有业务路由都在这里挂载。

# 从 FastAPI 导入 APIRouter（创建路由组用的类）。
from fastapi import APIRouter

# 每个业务模块导出自己的router；这里统一挂到带/api前缀的总路由。
from app.api.routes.ai_router import router as ai_router
from app.api.routes.auth_router import router as auth_router

# equipment_router自带/equipment前缀，负责管理员设备CRUD接口。
from app.api.routes.equipment_router import router as equipment_router

# files_router自带/files前缀，负责文件上传接口。
from app.api.routes.files_router import router as files_router
from app.api.routes.knowledge_router import router as knowledge_router
from app.api.routes.lab_router import router as lab_router
from app.api.routes.reservation_router import router as reservation_router

# users_router自带/user前缀，负责当前用户信息接口。
from app.api.routes.user_router import router as user_router

# 当前模板把 API 版本号统一放在汇总路由上。
# 子路由只关心自己的业务前缀，避免每个模块都重复写 /api。
api_router = APIRouter(prefix="/api")
# ↑ 创建一个汇总路由，所有挂进来的业务接口都会带 /api 前缀。
#   比如挂一个 /students 路由，最终地址就是 /api/students。
#   当前项目按教程使用 /api；如果以后教程引入API版本管理，再统一调整为 /api/v1。

# auth_router 自带 /auth，因此最终路径为 /api/auth/login。
api_router.include_router(auth_router)

# ai_router自带/ai前缀，因此聊天接口最终路径为POST /api/ai/chat。
# 如果忘记在总路由挂载，即使ai_router.py代码正确，FastAPI也不会暴露该接口。
api_router.include_router(ai_router)

# users_router挂载后形成/api/user/...。
api_router.include_router(user_router)

# equipment_router挂载后形成/api/equipment/...。
api_router.include_router(equipment_router)

api_router.include_router(lab_router)

# files_router挂载后，上传接口最终为POST /api/files/upload。
api_router.include_router(files_router)
api_router.include_router(reservation_router)
api_router.include_router(knowledge_router)

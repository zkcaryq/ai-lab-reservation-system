"""ORM Model 显式注册入口。

新 Model 在这里 ``from app.models.xxx import Xxx``；Alembic 通过 ``import app.models``
发现所有表，不会扫描文件系统。
"""

from app.models.ai_action_models import AIPendingAction
from app.models.ai_provider_models import AIProviderConfig, AIUsageRecord
from app.models.chat_models import ChatMessage, ChatSession
from app.models.equipment_models import Equipment
from app.models.knowledge_models import KnowledgeChunk, KnowledgeDocument
from app.models.lab_models import Lab
from app.models.reservation_models import Reservation
from app.models.user_models import User

__all__: list[str] = [
    "User",
    "Lab",
    "Equipment",
    "Reservation",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "ChatSession",
    "ChatMessage",
    "AIProviderConfig",
    "AIUsageRecord",
    "AIPendingAction",
]

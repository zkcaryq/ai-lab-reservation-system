"""AI 供应商注册表：按供应商名取实现。

业务层通过 get_provider(provider_name) 获取供应商适配器，不直接 import 具体实现。
新增供应商只需在 _PROVIDERS 登记即可，业务层零改动。
"""

from app.services.ai.providers.bailian import BailianProvider
from app.services.ai.providers.base import ChatProvider
from app.services.ai.providers.minimax import MiniMaxProvider

_PROVIDERS: dict[str, ChatProvider] = {
    MiniMaxProvider.provider_name: MiniMaxProvider(),
    BailianProvider.provider_name: BailianProvider(),
}


def get_provider(name: str) -> ChatProvider:
    """按供应商名返回适配器；未登记时抛 ValueError。"""

    provider = _PROVIDERS.get(name)
    if provider is None:
        raise ValueError(f"未登记的供应商：{name}")
    return provider

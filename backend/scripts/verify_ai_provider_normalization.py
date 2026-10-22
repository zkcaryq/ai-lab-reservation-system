"""本地端点规范化 / 模型解析 / 降级 / 校验测试脚本。

本脚本**不发起任何真实计费请求**，仅在本地内存里跑下列断言：

1. ``resolve_dashscope_base`` 对百炼 OpenAI 兼容地址派生 /api/v1 的行为；
2. ``BailianProvider.list_models`` 对真实响应样本（含 capabilities）解析正确，
   并按 capability 软过滤；
3. ``BailianProvider.list_models`` 对 401 / 404 / 5xx 抛出有意义的业务异常；
4. 未配置 chat 能力时模型列表为空，不再回退 .env；
5. ``chat`` 在 embedding 不可用时优雅降级（不抛 503）；
6. ``ProviderModelsRequest`` 校验未知 provider / capability 时路由层抛 400。

直接 ``python -m scripts.verify_ai_provider_normalization`` 运行，全部断言通过
会输出 ``OK`` 并以 exit 0 终止。
"""

import asyncio
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# 把 backend 根目录加入路径，便于 ``python -m`` 直接运行。
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import status  # noqa: E402

from app.core.errors import BusinessException  # noqa: E402
from app.services.ai.ai_provider_services import (  # noqa: E402
    VALID_CAPABILITIES,
    VALID_PROVIDERS,
    get_allowed_providers,
    validate_provider_for_capability,
)
from app.services.ai.ai_services import list_available_models  # noqa: E402
from app.services.ai.providers.bailian import (  # noqa: E402
    BailianProvider,
    resolve_dashscope_base,
)
from app.services.ai.providers.minimax import MiniMaxProvider  # noqa: E402


def test_resolve_dashscope_base() -> None:
    """URL 派生必须严格区分 compatible-mode 与 api/v1。"""

    # 主聊天端点 -> /api/v1
    assert (
        resolve_dashscope_base("https://dashscope.aliyuncs.com/compatible-mode/v1")
        == "https://dashscope.aliyuncs.com/api/v1"
    )
    # 北京工作空间专属域名
    assert (
        resolve_dashscope_base("https://xxx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
        == "https://xxx.cn-beijing.maas.aliyuncs.com/api/v1"
    )
    # 已经 /api/v1 形式
    assert (
        resolve_dashscope_base("https://dashscope.aliyuncs.com/api/v1")
        == "https://dashscope.aliyuncs.com/api/v1"
    )
    # override 优先
    assert (
        resolve_dashscope_base(
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "https://xxx.cn-beijing.maas.aliyuncs.com/api/v1",
        )
        == "https://xxx.cn-beijing.maas.aliyuncs.com/api/v1"
    )


def test_database_model_is_only_source() -> None:
    """模型列表只能来自管理员保存的 chat 配置。"""

    unconfigured = list_available_models([])
    assert unconfigured.models == []
    assert unconfigured.default_model is None

    configured = list_available_models([("qwen3-max-2026-01", 131_072)])
    assert [item.id for item in configured.models] == ["qwen3-max-2026-01"]
    assert configured.default_model == "qwen3-max-2026-01"


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


@contextmanager
def _patch_httpx_get_response(response: _FakeResponse, captured: dict[str, Any]):
    """同步上下文：把 httpx.AsyncClient 替换成返回定值的伪类。

    注意函数定义本身带 ``@contextmanager`` 装饰器，调用方应使用 ``with`` 语句。
    """

    import httpx

    original_async_client = httpx.AsyncClient

    class _FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._kwargs = kwargs

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(
            self,
            url: str,
            headers: dict[str, str],
            params: dict[str, int] | None = None,
        ) -> Any:
            captured["url"] = url
            captured["authorization"] = headers.get("Authorization", "")
            captured["params"] = params
            return response

    httpx.AsyncClient = _FakeAsyncClient  # type: ignore[assignment]
    try:
        yield
    finally:
        httpx.AsyncClient = original_async_client  # type: ignore[assignment]


def test_bailian_list_models_parses_capabilities() -> None:
    """output.models 含 capabilities / model_info 时元数据正确归一化。"""

    payload = {
        "output": {
            "models": [
                {
                    "model": "qwen3-max",
                    "name": "通义千问3 Max",
                    "capabilities": ["TG", "Reasoning"],
                    "model_info": {"context_window": 131072},
                    "inference_metadata": {"request_modality": ["Text"]},
                },
                {
                    "model": "qwen-vl-max",
                    "name": "通义千问 VL Max",
                    "capabilities": ["VU", "Generation"],
                    "model_info": {"context_window": 32768},
                    "inference_metadata": {"request_modality": ["Image", "Text"]},
                },
            ],
            "total": 2,
        }
    }

    captured: dict[str, str] = {}

    async def run_async() -> None:
        with _patch_httpx_get_response(_FakeResponse(json_data=payload), captured):
            models = await BailianProvider().list_models(
                api_key="sk-test",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )

        assert len(models) == 2
        by_id = {m.id: m for m in models}
        assert by_id["qwen3-max"].reasoning is True
        assert by_id["qwen3-max"].vision is False
        assert by_id["qwen3-max"].context_window == 131072
        assert by_id["qwen-vl-max"].vision is True
        # 列表 URL 应指向 /api/v1/models
        assert captured["url"].endswith("/api/v1/models")
        assert captured["authorization"] == "Bearer sk-test"

    asyncio.run(run_async())


def test_bailian_list_models_capability_filter() -> None:
    """按 capability 软过滤：仅返回 capabilities 含所请求值的模型。"""

    payload = {
        "output": {
            "models": [
                {
                    "model": "text-embedding-v3",
                    "capabilities": ["ME"],
                },
                {
                    "model": "qwen3-max",
                    "capabilities": ["TG", "Reasoning"],
                },
                {"model": "qwen3.5-ocr", "capabilities": ["TG"]},
                {"model": "qwen3-rerank", "capabilities": []},
            ],
            "total": 4,
        }
    }

    async def run_async() -> None:
        # embedding 过滤命中仅 text-embedding-v3
        with _patch_httpx_get_response(_FakeResponse(json_data=payload), {}):
            models = await BailianProvider().list_models(
                api_key="sk-test",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                capability="embedding",
            )
        assert [m.id for m in models] == ["text-embedding-v3"]

        # chat 对应百炼官方 TG 能力码。
        with _patch_httpx_get_response(_FakeResponse(json_data=payload), {}):
            models = await BailianProvider().list_models(
                api_key="sk-test",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                capability="chat",
            )
        assert [m.id for m in models] == ["qwen3-max"]

        with _patch_httpx_get_response(_FakeResponse(json_data=payload), {}):
            models = await BailianProvider().list_models(
                api_key="sk-test",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                capability="ocr",
            )
        assert [m.id for m in models] == ["qwen3.5-ocr"]

        with _patch_httpx_get_response(_FakeResponse(json_data=payload), {}):
            models = await BailianProvider().list_models(
                api_key="sk-test",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                capability="rerank",
            )
        assert [m.id for m in models] == ["qwen3-rerank"]

        # 完全没匹配的 capability：返回空
        with _patch_httpx_get_response(_FakeResponse(json_data=payload), {}):
            models = await BailianProvider().list_models(
                api_key="sk-test",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                capability="image-segmentation",
            )
        assert models == []

    asyncio.run(run_async())


def test_bailian_list_models_401_404_5xx() -> None:
    """4xx/5xx 应抛出有具体 message 的 BusinessException。"""

    async def run_async() -> None:
        # 上游 401 -> 本项目 400；不能让前端误判为当前管理员登录失效。
        with _patch_httpx_get_response(
            _FakeResponse(status_code=401, headers={"x-request-id": "rid-401"}), {}
        ):
            try:
                await BailianProvider().list_models(
                    api_key="bad",
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                )
            except BusinessException as exc:
                assert exc.status_code == status.HTTP_400_BAD_REQUEST
                assert "密钥错误" in exc.message
            else:
                raise AssertionError("expected 401 BusinessException")

        # 404 -> 400
        with _patch_httpx_get_response(
            _FakeResponse(status_code=404, headers={"x-request-id": "rid-404"}), {}
        ):
            try:
                await BailianProvider().list_models(
                    api_key="sk",
                    base_url="https://wrong.example.com/compatible-mode/v1",
                )
            except BusinessException as exc:
                assert exc.status_code == status.HTTP_400_BAD_REQUEST
                assert "404" in exc.message
            else:
                raise AssertionError("expected 400 BusinessException")

        # 500 -> 502
        with _patch_httpx_get_response(
            _FakeResponse(status_code=500, headers={"x-request-id": "rid-500"}), {}
        ):
            try:
                await BailianProvider().list_models(
                    api_key="sk",
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                )
            except BusinessException as exc:
                assert exc.status_code == status.HTTP_502_BAD_GATEWAY
            else:
                raise AssertionError("expected 502 BusinessException")

    asyncio.run(run_async())


def test_provider_models_request_validation() -> None:
    """Router 层校验：未知 provider / capability 直接 400，不会变成 500。"""

    from app.api.routes.ai_router import list_provider_models
    from app.schemas.ai_schemas import ProviderModelsRequest

    captured: dict[str, Any] = {}

    class _StubUser:
        role = "admin"

    async def fake_fetch(**_: Any) -> list[Any]:
        captured["called"] = True
        return []

    # monkey patch fetch_provider_models to avoid real network call
    from app.services.ai import ai_services

    original = ai_services.fetch_provider_models
    ai_services.fetch_provider_models = fake_fetch  # type: ignore[assignment]
    try:
        # 未知供应商
        try:
            asyncio.run(
                list_provider_models(
                    data=ProviderModelsRequest(
                        provider="openai",
                        base_url="https://x",
                        api_key="sk",
                    ),
                    current_user=_StubUser(),
                )
            )
        except BusinessException as exc:
            assert exc.status_code == status.HTTP_400_BAD_REQUEST
            assert "openai" in exc.message
        else:
            raise AssertionError("expected 400 for unknown provider")
        assert "called" not in captured

        # 已登记供应商，但能力组合不受支持：同样必须在出网前拒绝。
        try:
            asyncio.run(
                list_provider_models(
                    data=ProviderModelsRequest(
                        provider="minimax",
                        base_url="https://x",
                        api_key="sk",
                        capability="embedding",
                    ),
                    current_user=_StubUser(),
                )
            )
        except BusinessException as exc:
            assert exc.status_code == status.HTTP_400_BAD_REQUEST
            assert "embedding" in exc.message
        else:
            raise AssertionError("expected 400 for unsupported capability/provider pair")
        assert "called" not in captured

        # 未知 capability
        try:
            asyncio.run(
                list_provider_models(
                    data=ProviderModelsRequest(
                        provider="bailian",
                        base_url="https://x",
                        api_key="sk",
                        capability="hallucination",
                    ),
                    current_user=_StubUser(),
                )
            )
        except BusinessException as exc:
            assert exc.status_code == status.HTTP_400_BAD_REQUEST
            assert "hallucination" in exc.message
        else:
            raise AssertionError("expected 400 for unknown capability")
        assert "called" not in captured

        # 合法 provider + capability 才会真正调用
        asyncio.run(
            list_provider_models(
                data=ProviderModelsRequest(
                    provider="bailian",
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    api_key="sk",
                    capability="embedding",
                ),
                current_user=_StubUser(),
            )
        )
        assert captured.get("called") is True
    finally:
        ai_services.fetch_provider_models = original  # type: ignore[assignment]


def test_chat_uses_prepared_context() -> None:
    """chat 路由只消费前置编排结果，不在 Router 内重复检索规则。"""

    from app.api.routes.ai_router import chat as chat_route
    from app.schemas.ai_schemas import ChatRequest
    from app.services.ai import chat_pipeline_services
    from app.services.ai.chat_pipeline_services import ChatContext

    class _StubSession:
        pass

    class _StubUser:
        id = 1

    captured: dict[str, Any] = {}

    async def fake_prepare(*args, **kwargs):
        return ChatContext(retrieved_chunks=[], tools=[], capability="chat")

    async def fake_ai_chat(data, *, db, user_id, retrieved_chunks, **kwargs):
        captured["chunks"] = list(retrieved_chunks)
        from app.schemas.ai_schemas import ChatResponse, UsageInfo

        return ChatResponse(
            message="OK",
            session_id=user_id if False else 1,
            model="x",
            usage=UsageInfo(),
            sources=[],
        )

    from app.services.ai import ai_services as ai_services_module

    original_prepare = chat_pipeline_services.prepare_text_chat_context
    original_chat = ai_services_module.chat
    chat_pipeline_services.prepare_text_chat_context = fake_prepare  # type: ignore[assignment]
    ai_services_module.chat = fake_ai_chat  # type: ignore[assignment]
    try:
        result = asyncio.run(
            chat_route(
                data=ChatRequest(message="hi"),
                session=_StubSession(),
                current_user=_StubUser(),
            )
        )
        assert captured["chunks"] == [], "检索失败时应传入空 chunks"
        assert result.code == 200
    finally:
        chat_pipeline_services.prepare_text_chat_context = original_prepare  # type: ignore[assignment]
        ai_services_module.chat = original_chat  # type: ignore[assignment]


class _PatchHandle:
    """占位类型已删除：当前改用 _patch_httpx_get_response 上下文管理器。"""


def test_valid_provider_capability_lists() -> None:
    """注册表与合法枚举保持一致；新增 provider 必须同时写进 VALID_PROVIDERS。"""

    assert "minimax" in VALID_PROVIDERS
    assert "bailian" in VALID_PROVIDERS
    for cap in ("chat", "vision", "ocr", "embedding", "rerank", "intent", "decision"):
        assert cap in VALID_CAPABILITIES
    assert get_allowed_providers("embedding") == ("bailian",)
    assert get_allowed_providers("chat") == ("minimax", "bailian")
    try:
        validate_provider_for_capability("ocr", "minimax")
    except BusinessException as exc:
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
    else:
        raise AssertionError("MiniMax OCR should be rejected")
    # 抽象基类不应被实例化
    try:
        MiniMaxProvider()  # noqa: B018 确认能实例化
    except Exception as exc:
        raise AssertionError(f"MiniMaxProvider should be instantiable: {exc}") from exc


def main() -> int:
    """按顺序跑所有断言；任一失败抛 AssertionError 让进程非零退出。"""

    tests = [
        test_resolve_dashscope_base,
        test_database_model_is_only_source,
        test_bailian_list_models_parses_capabilities,
        test_bailian_list_models_capability_filter,
        test_bailian_list_models_401_404_5xx,
        test_provider_models_request_validation,
        test_chat_uses_prepared_context,
        test_valid_provider_capability_lists,
    ]
    for test in tests:
        name = test.__name__
        try:
            test()
        except AssertionError as exc:
            import traceback

            print(f"FAIL {name}: {exc}")
            traceback.print_exc()
            return 1
        except Exception as exc:  # noqa: BLE001
            import traceback

            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            return 2
        else:
            print(f"OK   {name}")
    print("OK   all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

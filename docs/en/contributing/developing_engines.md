# awesome_engine.py (假设 awesome_sdk 是同步的)
import asyncio
from trans_hub.engines.base import BaseTranslationEngine
# ...

class AwesomeEngine(BaseTranslationEngine[...]):
    # ...

    def _translate_single_sync(self, text: str) -> EngineBatchItemResult:
        """[私有] 这是一个执行阻塞操作的同步方法。"""
        # ... 同步的 API 调用逻辑 ...

    async def _atranslate_one(self, text: str, ...) -> EngineBatchItemResult:
        """[实现] 这是必须实现的异步接口。"""
        # 使用 asyncio.to_thread 将同步方法包装成一个可等待对象
        return await asyncio.to_thread(self._translate_single_sync, text)


# awesome_engine.py
from trans_hub.engines.base import BaseContextModel

class AwesomeEngineContext(BaseContextModel):
    # 允许用户通过 context={"tone": "formal"} 来指定语气
    tone: Optional[str] = None


# awesome_engine.py

class AwesomeEngine(BaseTranslationEngine[...]):
    # 别忘了在类属性中注册你的 Context 模型
    CONTEXT_MODEL = AwesomeEngineContext

    async def _atranslate_one(self, ..., context_config: dict[str, Any]) -> ...:
        tone = context_config.get("tone", "neutral") # 从上下文中获取 'tone'

        # 在你的 API 调用中使用 tone
        translated_text = await self.client.translate(..., tone=tone)
        # ...


# trans_hub/engines/awesome_engine.py (完整示例)

import asyncio
from typing import Any, Optional

from pydantic_settings import BaseSettings

from trans_hub.engines.base import BaseEngineConfig, BaseTranslationEngine
from trans_hub.engines.meta import register_engine_config
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

# 假设有一个名为 'awesome_sdk' 的同步第三方库
try:
    import awesome_sdk
except ImportError:
    awesome_sdk = None


# --- 1. 定义配置模型 ---
class AwesomeEngineConfig(BaseSettings, BaseEngineConfig):
    # BaseSettings 会自动从 .env 和环境变量加载 (前缀: TH_)
    awesome_api_key: str


# --- 2. 定义引擎主类 ---
class AwesomeEngine(BaseTranslationEngine[AwesomeEngineConfig]):
    CONFIG_MODEL = AwesomeEngineConfig
    VERSION = "1.0.0"

    def __init__(self, config: AwesomeEngineConfig):
        super().__init__(config)
        if awesome_sdk is None:
            raise ImportError("要使用 AwesomeEngine，请先安装 'awesome-sdk' 库")
        self.client = awesome_sdk.Client(api_key=config.awesome_api_key)

    def _translate_single_sync(self, text: str, target_lang: str) -> EngineBatchItemResult:
        """[私有] 这是一个执行阻塞 I/O 的同步方法。"""
        try:
            translated_text = self.client.translate(text=text, target_language=target_lang)
            return EngineSuccess(translated_text=translated_text)
        except awesome_sdk.AuthError as e:
            return EngineError(error_message=f"认证错误: {e}", is_retryable=False)
        except Exception as e:
            return EngineError(error_message=f"未知错误: {e}", is_retryable=True)

    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[实现] 通过 asyncio.to_thread 包装同步调用。"""
        return await asyncio.to_thread(self._translate_single_sync, text, target_lang)


# --- 3. 自我注册 ---
# 将引擎名 "awesome" 与其配置模型 AwesomeEngineConfig 关联起来
register_engine_config("awesome", AwesomeEngineConfig)


# tests/engines/test_awesome_engine.py
import pytest
from trans_hub.config import TransHubConfig
# ...

@pytest.mark.asyncio
async def test_coordinator_with_awesome_engine(monkeypatch, ...):
    # 1. 模拟外部依赖
    # ...
    
    # 2. 通过 monkeypatch 设置环境变量
    monkeypatch.setenv("TH_AWESOME_API_KEY", "fake-key")

    # 3. 只需激活引擎，配置会自动被创建和加载
    config = TransHubConfig(active_engine="awesome")
    
    # ... (后续的 Coordinator 初始化和测试逻辑) ...


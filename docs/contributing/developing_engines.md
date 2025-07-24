# 指南：开发一个新引擎

欢迎你，未来的贡献者！本指南将带你一步步地为 `Trans-Hub` 开发一个全新的翻译引擎。得益于 `Trans-Hub` 的**纯异步**和**动态发现**架构，这个过程比你想象的要简单得多。

## 目录

1. [开发哲学：引擎的职责](#1-开发哲学引擎的职责)
2. [开发流程：三步完成](#2-开发流程三步完成)
3. [异步适配：处理同步库](#3-异步适配处理同步库)
4. [编写测试：验证你的引擎](#4-编写测试验证你的引擎)
5. [一份完整的示例：`AwesomeEngine`](#5-一份完整的示例awesomeengine)

---

### **1. 开发哲学：引擎的职责**

在 `Trans-Hub` 的架构中，一个 `Engine` 的职责被严格限定在：

- **实现一个 `async def atranslate_batch(...)` 方法**。
- 接收一个字符串列表、目标语言等参数。
- 与一个特定的外部翻译 API 进行通信。
- 将 API 的成功和失败结果，包装成 `EngineSuccess` 或 `EngineError` 对象。
- 返回一个结果列表，其顺序和长度必须与输入完全对应。

引擎**不需要**关心：

- 数据库操作、缓存、重试、速率限制等。这些都由 `Coordinator` 处理。
- **同步/异步的协调**。`Coordinator` 只会调用 `atranslate_batch`，你的引擎必须提供一个正确的异步实现。

### **2. 开发流程：三步完成**

假设我们要创建一个对接 “Awesome Translate” 服务的引擎。

#### **第一步：创建引擎文件**

在 `trans_hub/engines/` 目录下，创建一个新的 Python 文件，例如 **`awesome_engine.py`**。

#### **第二步：实现引擎代码**

打开 `awesome_engine.py` 文件，编写引擎的核心逻辑。这通常包含三个部分：

1.  **配置模型**: 定义一个继承自 `BaseEngineConfig` 的 Pydantic 模型，用于存放 API Key 等配置。如果配置需要从 `.env` 文件加载，请同时继承 `pydantic_settings.BaseSettings`。
2.  **引擎主类**: 实现一个继承自 `BaseTranslationEngine` 的主类。
3.  **核心逻辑**: 在 `atranslate_batch` 方法中实现与外部 API 的通信。

> ⚠️ **重要提示：`EngineError` 的正确使用**
> 当你的引擎遇到 API 错误时，你**不应该** `raise EngineError(...)`。正确做法是，将 `EngineError` 对象作为结果列表的一项 **`return`** 回去。`Coordinator` 期望收到一个与输入列表长度完全对应的结果列表。

#### **第三步：注册引擎配置**

在 `trans_hub/config.py` 的 `EngineConfigs` 模型中，添加你的引擎配置字段。字段名必须是小写的引擎名（例如 `awesome`）。

```python
# trans_hub/config.py
from trans_hub.engines.awesome_engine import AwesomeEngineConfig
# ...

class EngineConfigs(BaseModel):
    # ... 其他引擎配置 ...
    awesome: Optional[AwesomeEngineConfig] = None
```

**完成了！** `engine_registry` 会在你下次运行程序时自动发现你的 `AwesomeEngine`。

### **3. 异步适配：处理同步库**

这是为 `Trans-Hub` 开发引擎最关键的一点。

- **如果你的目标 API 提供了 `asyncio` 客户端** (例如 `openai` 库)，请直接在 `atranslate_batch` 中使用 `await` 调用它。
- **如果你的目标 API 只有一个同步的、阻塞的库** (例如 `translators` 库)，你**必须**使用 `asyncio.to_thread` 来包装这个阻塞调用。这会将同步代码放到一个独立的线程中执行，从而避免阻塞主事件循环。

**这是适配同步库的“黄金范例”**:

```python
# awesome_engine.py (假设 awesome_sdk 是同步的)
import asyncio
from trans_hub.engines.base import BaseTranslationEngine
# ...

class AwesomeEngine(BaseTranslationEngine[...]):
    # ...

    def _translate_single_sync(self, text: str) -> EngineBatchItemResult:
        """这是一个私有的、执行阻塞操作的同步方法。"""
        try:
            # awesome_sdk.translate(...) 是一个阻塞的网络调用
            result = self.client.translate(text)
            return EngineSuccess(translated_text=result)
        except Exception as e:
            return EngineError(error_message=str(e), is_retryable=True)

    async def atranslate_batch(
        self, texts: list[str], ...
    ) -> list[EngineBatchItemResult]:
        """这是公共的异步接口。"""
        tasks = [
            # 使用 asyncio.to_thread 将同步方法包装成一个可等待对象
            asyncio.to_thread(self._translate_single_sync, text)
            for text in texts
        ]
        results = await asyncio.gather(*tasks)
        return list(results)
```

### **4. 编写测试：验证你的引擎**

为你的引擎编写异步测试是至关重要的。我们推荐使用 `pytest` 和 `pytest-asyncio`。

```python
# tests/test_awesome_engine.py
import pytest
from unittest.mock import MagicMock, patch

from trans_hub.config import TransHubConfig, EngineConfigs
from trans_hub.coordinator import Coordinator
from trans_hub.engines.awesome_engine import AwesomeEngineConfig
# ...

@pytest.mark.asyncio
# 使用 patch 来模拟外部 awesome_sdk 库
@patch('trans_hub.engines.awesome_engine.awesome_sdk')
async def test_coordinator_with_awesome_engine(mock_sdk, mock_persistence_handler):
    """测试 Coordinator 是否能成功驱动 AwesomeEngine。"""
    # 1. 模拟 SDK 的行为
    mock_sdk.Client.return_value.translate.return_value = "你好，世界！"

    # 2. 配置 Trans-Hub
    config = TransHubConfig(
        active_engine="awesome",
        engine_configs=EngineConfigs(
            awesome=AwesomeEngineConfig(awesome_api_key="fake-key")
        )
    )
    coordinator = Coordinator(config=config, persistence_handler=mock_persistence_handler)
    await coordinator.initialize()

    # 3. 异步执行翻译流程
    results = [res async for res in coordinator.process_pending_translations(target_lang="zh-CN")]

    # 4. 断言结果
    assert len(results) == 1
    assert results[0].translated_content == "你好，世界！"
    assert results[0].engine == "awesome"

    # 5. 清理
    await coordinator.close()
```

### **5. 一份完整的示例：`AwesomeEngine`**

下面是一个完整的、遵循所有最佳实践的 `awesome_engine.py` 文件示例。

```python
# trans_hub/engines/awesome_engine.py (完整示例)

import asyncio
from typing import Optional, List

from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.engines.base import BaseTranslationEngine, BaseEngineConfig, BaseContextModel
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

# 假设 awesome_sdk 是一个同步的第三方库
try:
    import awesome_sdk
except ImportError:
    awesome_sdk = None


# 1. 配置模型
class AwesomeEngineConfig(BaseSettings, BaseEngineConfig):
    model_config = SettingsConfigDict(env_prefix="TH_")
    awesome_api_key: str


# 2. 引擎主类
class AwesomeEngine(BaseTranslationEngine[AwesomeEngineConfig]):
    CONFIG_MODEL = AwesomeEngineConfig
    VERSION = "1.0.0"

    def __init__(self, config: AwesomeEngineConfig):
        super().__init__(config)
        if awesome_sdk is None:
            raise ImportError("要使用 AwesomeEngine，请先安装 'awesome-sdk' 库")

        self.client = awesome_sdk.Client(api_key=self.config.awesome_api_key)

    def _translate_single_sync(self, text: str, target_lang: str) -> EngineBatchItemResult:
        """[私有] 这是一个执行阻塞 I/O 的同步方法。"""
        try:
            translated_text = self.client.translate(text=text, target_language=target_lang)
            return EngineSuccess(translated_text=translated_text)
        except awesome_sdk.AuthError as e:
            return EngineError(error_message=f"认证错误: {e}", is_retryable=False)
        except Exception as e:
            return EngineError(error_message=f"未知错误: {e}", is_retryable=True)

    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """
        [公有] 纯异步接口。
        通过 asyncio.to_thread 将同步的阻塞调用放到独立的线程中执行。
        """
        tasks = [
            asyncio.to_thread(self._translate_single_sync, text, target_lang)
            for text in texts
        ]
        results = await asyncio.gather(*tasks)
        return list(results)
```

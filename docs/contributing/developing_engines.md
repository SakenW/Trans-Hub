# 指南：开发一个新引擎

欢迎你，未来的贡献者！本指南将带你一步步地为 `Trans-Hub` 开发一个全新的翻译引擎。得益于 `Trans-Hub` 的**纯异步**、**动态发现**和**基类驱动**的架构，这个过程比你想象的要简单得多。

## 目录

1. [开发哲学：引擎的职责](#1-开发哲学引擎的职责)
2. [核心模式：只实现 `_atranslate_one`](#2-核心模式只实现-_atranslate_one)
3. [开发流程：两步完成](#3-开发流程两步完成)
4. [异步适配：处理同步库](#4-异步适配处理同步库)
5. [一份完整的示例：`AwesomeEngine`](#5-一份完整的示例awesomeengine)
6. [编写测试：验证你的引擎](#6-编写测试验证你的引擎)

---

### **1. 开发哲学：引擎的职责**

在 `Trans-Hub` 的架构中，一个 `Engine` 的职责被严格限定在：

- **实现一个 `async def _atranslate_one(...)` 方法**。
- 接收**一个**字符串、目标语言等参数。
- 与一个特定的外部翻译 API 进行通信。
- 将 API 的成功或失败结果，包装成 `EngineSuccess` 或 `EngineError` 对象并 **`return`**。

引擎**不需要**关心：

- **批处理和并发**：`BaseTranslationEngine` 会自动处理 `asyncio.gather` 的逻辑。
- **上下文解析**：基类会处理 `context` 并将结果作为 `context_config` 字典传入你的方法。
- **数据库、缓存、重试、速率限制**：这些都由 `Coordinator` 处理。

> ⚠️ **重要提示：`EngineError` 的正确使用**
> 当你的引擎遇到 API 错误时，你**不应该** `raise EngineError(...)`。正确做法是，将 `EngineError` 对象作为结果 **`return`** 回去。

### **2. 核心模式：只实现 `_atranslate_one`**

这是为 `Trans-Hub` v2.0+ 开发引擎的**唯一核心要求**。你的引擎主类必须继承 `BaseTranslationEngine`，但你**唯一**需要重写的方法就是 `_atranslate_one`。

```python
# your_engine.py

# ... imports ...
from trans_hub.engines.base import BaseTranslationEngine
from trans_hub.types import EngineBatchItemResult

class YourEngine(BaseTranslationEngine[...]):
    # ...

    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any], # 基类已为你解析好的上下文
    ) -> EngineBatchItemResult:
        #
        # 在这里实现你与外部 API 的通信逻辑
        # 只需处理单个 `text` 的翻译
        #
        # ...
        # return EngineSuccess(...) or EngineError(...)
```

你**不应该**重写 `atranslate_batch` 方法，所有批处理逻辑都已在基类中为你准备好了。

### **3. 开发流程：两步完成**

假设我们要创建一个对接 “Awesome Translate” 服务的引擎。

#### **第一步：创建引擎文件**

在 `trans_hub/engines/` 目录下，创建一个新的 Python 文件，例如 **`awesome_engine.py`**。

#### **第二步：实现引擎代码**

打开 `awesome_engine.py` 文件，编写引擎的核心逻辑。这通常包含三个部分：

1.  **配置模型**: 定义一个继承自 `BaseEngineConfig` 的 Pydantic 模型，用于存放 API Key 等配置。如果配置需要从 `.env` 文件加载，请同时继承 `pydantic_settings.BaseSettings`。
2.  **引擎主类**: 实现一个继承自 `BaseTranslationEngine` 的主类。
3.  **核心逻辑**: 在 `_atranslate_one` 方法中实现与外部 API 的通信。

**完成了！** `Trans-Hub` 的动态发现和智能配置系统会处理剩下的一切。你**不需要**手动去 `trans_hub/config.py` 中注册任何东西。当用户在 `TransHubConfig` 中设置 `active_engine="awesome"` 时，系统会自动发现你的引擎并为其创建默认配置实例。

### **4. 异步适配：处理同步库**

这是适配同步库的“黄金范例”，它展示了如何在 `_atranslate_one` 中使用 `asyncio.to_thread`。

```python
# awesome_engine.py (假设 awesome_sdk 是同步的)
import asyncio
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
```

### **5. 进阶技巧：支持自定义上下文**

`Trans-Hub` 的一个强大功能是允许在翻译请求中传递 `context` 字典。要让你的引擎能够利用这些上下文，你需要做两件事：

1.  **定义一个 `ContextModel`**: 在你的引擎文件中，创建一个继承自 `BaseContextModel` 的 Pydantic 模型，并定义你希望从 `context` 中接收的字段。

    ```python
    # awesome_engine.py
    from trans_hub.engines.base import BaseContextModel

    class AwesomeEngineContext(BaseContextModel):
        # 允许用户通过 context={"tone": "formal"} 来指定语气
        tone: Optional[str] = None
    ```

2.  **在 `_atranslate_one` 中使用 `context_config`**: 基类会自动验证 `context` 并将结果以字典形式传入 `context_config` 参数。你只需在你的核心逻辑中使用它。

    ```python
    # awesome_engine.py
    
    class AwesomeEngine(BaseTranslationEngine[...]):
        # 别忘了在类属性中注册你的 Context 模型
        CONTEXT_MODEL = AwesomeEngineContext
        
        async def _atranslate_one(self, ..., context_config: dict[str, Any]) -> ...:
            tone = context_config.get("tone", "neutral") # 从上下文中获取 'tone'
            
            # 在你的 API 调用中使用 tone
            translated_text = await self.client.translate(..., tone=tone)
            # ...
    ```

通过这种方式，你可以为你的引擎创建出非常强大和灵活的自定义功能。

### **6. 一份完整的示例：`AwesomeEngine`**

下面是一个完整的、遵循所有最新最佳实践的 `awesome_engine.py` 文件示例。

```python
# trans_hub/engines/awesome_engine.py (完整示例)

import asyncio
from typing import Any, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.engines.base import BaseEngineConfig, BaseTranslationEngine
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

    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[公有] 纯异步接口实现。"""
        return await asyncio.to_thread(
            self._translate_single_sync, text, target_lang
        )
```

### **7. 编写测试：验证你的引擎**

为你的引擎编写异步测试是至关重要的。由于所有业务逻辑都由 `Coordinator` 驱动，测试 `Coordinator` 能否成功使用你的新引擎是最好的集成测试方法。

```python
# tests/engines/test_awesome_engine.py
import pytest
from unittest.mock import MagicMock, patch

from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator
# ...

@pytest.mark.asyncio
# 使用 patch 来模拟外部 awesome_sdk 库
@patch('trans_hub.engines.awesome_engine.awesome_sdk')
async def test_coordinator_with_awesome_engine(mock_sdk, mock_persistence_handler):
    """测试 Coordinator 是否能成功驱动 AwesomeEngine。"""
    # 1. 模拟 SDK 的行为
    mock_sdk.Client.return_value.translate.return_value = "你好，世界！"

    # 2. 配置 Trans-Hub 来使用你的引擎
    # 注意：我们不需要手动创建 AwesomeEngineConfig。
    # 我们只需设置 .env 环境变量 (通过 monkeypatch) 或依赖默认值。
    # 这里为了简单，我们直接在测试中断言它被正确调用。
    config = TransHubConfig(active_engine="awesome")

    # 假设你的 AwesomeEngineConfig 配置了 awesome_api_key
    # 在测试中，你可能需要用 monkeypatch 来设置环境变量
    # monkeypatch.setenv("TH_AWESOME_API_KEY", "fake-key")

    coordinator = Coordinator(config=config, persistence_handler=mock_persistence_handler)
    await coordinator.initialize()

    # 3. 异步执行翻译流程
    # ...
```

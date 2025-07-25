# 指南：开发一个新引擎

欢迎你，未来的贡献者！本指南将带你一步步地为 `Trans-Hub` 开发一个全新的翻译引擎。得益于 `Trans-Hub` 的**纯异步**、**动态发现**和**自我注册**的架构，这个过程比你想象的要简单得多。

在开始之前，我们假设你已经对 `Trans-Hub` 的[核心架构](../architecture/01_overview.md)有了基本的了解。

## 目录

1. [开发哲学：引擎的职责](#1-开发哲学引擎的职责)
2. [核心模式：只实现 `_atranslate_one`](#2-核心模式只实现-_atranslate_one)
3. [开发流程：三步完成](#3-开发流程三步完成)
4. [异步适配：处理同步库](#4-异步适配处理同步库)
5. [进阶技巧：支持自定义上下文](#5-进阶技巧支持自定义上下文)
6. [一份完整的示例：`AwesomeEngine`](#6-一份完整的示例awesomeengine)
7. [编写测试：验证你的引擎](#7-编写测试验证你的引擎)

---

### **1. 开发哲学：引擎的职责**

在 `Trans-Hub` 的架构中，一个 `Engine` 的职责被严格限定在：

- **实现一个 `async def _atranslate_one(...)` 方法**。
- 接收**一个**字符串、目标语言等参数。
- 与一个特定的外部翻译 API 进行通信。
- 将 API 的成功或失败结果，包装成 `EngineSuccess` 或 `EngineError` 对象并 **`return`**。

引擎**不需要**关心：

- **批处理和并发**：`BaseTranslationEngine` 会自动处理。
- **配置加载与发现**：`TransHubConfig` 和注册表会自动处理。
- **数据库、缓存、重试、速率限制**：这些都由 `Coordinator` 处理。

### **2. 核心模式：只实现 `_atranslate_one`**

这是为 `Trans-Hub` v2.1+ 开发引擎的**唯一核心要求**。你的引擎主类必须继承 `BaseTranslationEngine`，但你**唯一**需要重写的方法就是 `_atranslate_one`。基类已经为你处理了所有外围的批处理逻辑。

### **3. 开发流程：三步完成**

假设我们要创建一个对接 “Awesome Translate” 服务的引擎。

#### **第一步：创建引擎文件**

在 `trans_hub/engines/` 目录下，创建一个新的 Python 文件，例如 **`awesome_engine.py`**。

#### **第二步：实现引擎代码**

打开 `awesome_engine.py` 文件，并遵循以下结构编写代码。这是构建一个新引擎的“黄金模板”。

1.  **导入**: 在文件顶部，导入所有必要的模块，包括 `BaseTranslationEngine` 和 `register_engine_config` 函数。
2.  **定义配置模型 (`...Config`)**: 创建一个继承自 `BaseEngineConfig` 的 Pydantic 模型。如果需要从 `.env` 加载配置，请同时继承 `pydantic_settings.BaseSettings`。
3.  **定义引擎主类 (`...Engine`)**: 创建一个继承自 `BaseTranslationEngine` 的主类，并实现 `_atranslate_one` 方法。
4.  **自我注册**: 在**文件末尾**，调用 `register_engine_config` 函数，将你的引擎名和配置类关联起来。

#### **第三步：坐享其成**

**完成了！** 你**不需要**再修改任何其他文件。

- `engine_registry.py` 会在你下次运行程序时**自动发现**你的 `AwesomeEngine` 类。
- `config.py` 会通过元数据注册表**自动发现**你的 `AwesomeEngineConfig` 类。

当用户在 `TransHubConfig` 中设置 `active_engine="awesome"` 时，整个系统会自动协同工作。

### **4. 异步适配：处理同步库**

- **如果你的目标 API 提供了 `asyncio` 客户端** (例如 `openai` 库)，请直接在 `_atranslate_one` 中使用 `await` 调用它。
- **如果你的目标 API 只有一个同步的、阻塞的库** (例如 `translators` 库)，你**必须**使用 `asyncio.to_thread` 来包装这个阻塞调用，以避免阻塞主事件循环。

**这是适配同步库的“黄金范例”**:

```python
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

### **6. 一份完整的示例：`AwesomeEngine`**

下面是一个完整的、遵循所有最佳实践的 `awesome_engine.py` 文件示例。你可以直接以此为模板开始你的开发。

```python
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
```

### **7. 编写测试：验证你的引擎**

为你的引擎编写异步测试是至关重要的。由于所有业务逻辑都由 `Coordinator` 驱动，测试 `Coordinator` 能否成功使用你的新引擎是最好的集成测试方法。

```python
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
```
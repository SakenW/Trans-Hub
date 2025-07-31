# Guide: Developing a New Engine

Welcome, future contributor! This guide will take you step by step to develop a brand new translation engine for `Trans-Hub`. Thanks to the **purely asynchronous**, **dynamic discovery**, and **self-registration** architecture of `Trans-Hub`, this process is much simpler than you might think.

Before we begin, we assume that you have a basic understanding of the core architecture of `Trans-Hub`.

## Table of Contents

1. [Development Philosophy: Responsibilities of the Engine](#1-Development-Philosophy-Responsibilities-of-the-Engine)  
2. [Core Pattern: Implementing `_atranslate_one`](#2-Core-Pattern-Implementing-_atranslate_one)  
3. [Development Process: Completed in Three Steps](#3-Development-Process-Completed-in-Three-Steps)  
4. [Asynchronous Adaptation: Handling Synchronous Libraries](#4-Asynchronous-Adaptation-Handling-Synchronous-Libraries)  
5. [Advanced Techniques: Supporting Custom Contexts](#5-Advanced-Techniques-Supporting-Custom-Contexts)  
6. [A Complete Example: `AwesomeEngine`](#6-A-Complete-Example-AwesomeEngine)  
7. [Writing Tests: Validate Your Engine](#7-Writing-Tests-Validate-Your-Engine)

### **1. Development Philosophy: The Responsibilities of the Engine**

In the architecture of `Trans-Hub`, the responsibilities of an `Engine` are strictly defined as:

- **Implement an `async def _atranslate_one(...)` method**.
- Accept **one** string, target language, and other parameters.
- Communicate with a specific external translation API.
- Wrap the API's success or failure result into `EngineSuccess` or `EngineError` objects and **`return`**.

The engine **does not need** to worry about:

- **Batch processing and concurrency**: `BaseTranslationEngine` will handle it automatically.
- **Configuration loading and discovery**: `TransHubConfig` and the registry will handle it automatically.
- **Database, caching, retries, rate limiting**: These are handled by `Coordinator`.

### **2. Core Mode: Implement only `_atranslate_one`**

This is the **only core requirement** for developing the `Trans-Hub` v2.1+ engine. Your engine's main class must inherit from `BaseTranslationEngine`, but the **only** method you need to override is `_atranslate_one`. The base class has already handled all the surrounding batch processing logic for you.

### **3. Development Process: Completed in Three Steps**

Assuming we want to create an engine that interfaces with the 'Awesome Translate' service.

#### **Step 1: Create Engine File**

Create a new Python file in the `trans_hub/engines/` directory, for example **`awesome_engine.py`**.

#### **Step 2: Implement Engine Code**

Open the `awesome_engine.py` file and follow the structure below to write the code. This is the "golden template" for building a new engine.

1. **Import**: At the top of the file, import all necessary modules, including `BaseTranslationEngine` and the `register_engine_config` function.  
2. **Define Configuration Model (`...Config`)**: Create a Pydantic model that inherits from `BaseEngineConfig`. If you need to load configurations from `.env`, also inherit from `pydantic_settings.BaseSettings`.  
3. **Define Engine Main Class (`...Engine`)**: Create a main class that inherits from `BaseTranslationEngine` and implement the `_atranslate_one` method.  
4. **Self-registration**: At the **end of the file**, call the `register_engine_config` function to associate your engine name with the configuration class.

#### **Step Three: Reap the Benefits**

**Done!** You **don't need** to modify any other files.

- `engine_registry.py` will **automatically discover** your `AwesomeEngine` class the next time you run the program.
- `config.py` will **automatically discover** your `AwesomeEngineConfig` class through the metadata registry.

When the user sets `active_engine="awesome"` in `TransHubConfig`, the entire system will work together automatically.

### **4. Asynchronous Adaptation: Handling Synchronous Libraries**

- **If your target API provides an `asyncio` client** (such as the `openai` library), please use `await` to call it directly in `_atranslate_one`.
- **If your target API only has a synchronous, blocking library** (such as the `translators` library), you **must** use `asyncio.to_thread` to wrap this blocking call to avoid blocking the main event loop.

This is the "golden example" for adapting synchronization libraries.

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

### **5. Advanced Techniques: Support for Custom Context**

A powerful feature of `Trans-Hub` is the ability to pass a `context` dictionary in translation requests. To enable your engine to utilize this context, you need to do two things:

1.  **Define a `ContextModel`**: In your engine file, create a Pydantic model that inherits from `BaseContextModel` and define the fields you want to receive from the `context`.

    ```python
    # awesome_engine.py
    from trans_hub.engines.base import BaseContextModel

    class AwesomeEngineContext(BaseContextModel):
        # Allow users to specify tone via context={"tone": "formal"}
        tone: Optional[str] = None
    ```

2.  **Use `context_config` in `_atranslate_one`**: The base class will automatically validate the `context` and pass the result as a dictionary to the `context_config` parameter. You just need to use it in your core logic.

    ```python
    # awesome_engine.py
    
    class AwesomeEngine(BaseTranslationEngine[...]):
        # Don't forget to register your Context model in the class attribute
        CONTEXT_MODEL = AwesomeEngineContext
        
        async def _atranslate_one(self, ..., context_config: dict[str, Any]) -> ...:
            tone = context_config.get("tone", "neutral") # Get 'tone' from context
            
            # Use tone in your API call
            translated_text = await self.client.translate(..., tone=tone)
            # ...
    ```

### **6. A Complete Example: `AwesomeEngine`**

Here is a complete `awesome_engine.py` file example that follows all best practices. You can use this as a template to start your development.

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

### **7. Writing Tests: Validate Your Engine**

It is essential to write asynchronous tests for your engine. Since all business logic is driven by the `Coordinator`, testing whether the `Coordinator` can successfully use your new engine is the best method for integration testing.

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

# Guide: Developing a New Engine

Welcome, future contributor! This guide will take you step by step to develop a brand new translation engine for `Trans-Hub`. Thanks to the **purely asynchronous**, **dynamic discovery**, and **self-registration** architecture of `Trans-Hub`, this process is much simpler than you might think.

Before we begin, we assume that you have a basic understanding of the core architecture of `Trans-Hub`.

## Table of Contents

1. [Development Philosophy: Responsibilities of the Engine](#1-Development-Philosophy-Responsibilities-of-the-Engine)  
2. [Core Pattern: Only Implement `_atranslate_one`](#2-Core-Pattern-Only-Implement-_atranslate_one)  
3. [Development Process: Completed in Three Steps](#3-Development-Process-Completed-in-Three-Steps)  
4. [Asynchronous Adaptation: Handling Synchronous Libraries](#4-Asynchronous-Adaptation-Handling-Synchronous-Libraries)  
5. [Advanced Techniques: Supporting Custom Contexts](#5-Advanced-Techniques-Supporting-Custom-Contexts)  
6. [A Complete Example: `AwesomeEngine`](#6-A-Complete-Example-AwesomeEngine)  
7. [Writing Tests: Validate Your Engine](#7-Writing-Tests-Validate-Your-Engine)

It seems there is no text provided for translation. Please provide the text you would like to have translated.

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

### **2. Core Mode: Only Implement `_atranslate_one`**

This is the **only core requirement** for developing the `Trans-Hub` v2.1+ engine. Your engine's main class must inherit from `BaseTranslationEngine`, but the **only** method you need to override is `_atranslate_one`. The base class has already handled all the surrounding batch processing logic for you.

### **3. Development Process: Completed in Three Steps**

Assuming we want to create an engine that interfaces with the 'Awesome Translate' service.

#### **Step 1: Create Engine File**

Create a new Python file in the `trans_hub/engines/` directory, for example **`awesome_engine.py`**.

#### **Step 2: Implement Engine Code**

Open the `awesome_engine.py` file and follow the structure below to write the code. This is the "golden template" for building a new engine.

1.  **Import**: At the top of the file, import all necessary modules, including `BaseTranslationEngine` and the `register_engine_config` function.  
2.  **Define Configuration Model (`...Config`)**: Create a Pydantic model that inherits from `BaseEngineConfig`. If you need to load configurations from `.env`, also inherit from `pydantic_settings.BaseSettings`.  
3.  **Define Engine Main Class (`...Engine`)**: Create a main class that inherits from `BaseTranslationEngine` and implement the `_atranslate_one` method.  
4.  **Self-registration**: At the **end of the file**, call the `register_engine_config` function to associate your engine name with the configuration class.

#### **Step Three: Reap the Benefits**

**Completed!** You **don't need** to modify any other files.

- `engine_registry.py` will **automatically discover** your `AwesomeEngine` class the next time you run the program.
- `config.py` will **automatically discover** your `AwesomeEngineConfig` class through the metadata registry.

When the user sets `active_engine="awesome"` in `TransHubConfig`, the entire system will work together automatically.

### **4. Asynchronous Adaptation: Handling Synchronous Libraries**

- **If your target API provides an `asyncio` client** (for example, the `openai` library), please use `await` to call it directly in `_atranslate_one`.
- **If your target API only has a synchronous, blocking library** (for example, the `translators` library), you **must** use `asyncio.to_thread` to wrap this blocking call to avoid blocking the main event loop.

This is the "golden example" for adapting synchronization libraries.

```python
# awesome_engine.py (假设 awesome_sdk 是同步的)
import asyncio
from trans_hub.engines.base import BaseTranslationEngine
# ...

class AwesomeEngine(BaseTranslationEngine[...]):
    # ...

    def _translate_single_sync(self, text: str) -> EngineBatchItemResult:
        """[Private] This is a synchronous method that performs a blocking operation."""
        # ... Logic for synchronous API calls ...

    async def _atranslate_one(self, text: str, ...) -> EngineBatchItemResult:
        """[Implementation] This is an asynchronous interface that must be implemented."""
        # Use asyncio.to_thread to wrap the synchronous method into an awaitable object
        return await asyncio.to_thread(self._translate_single_sync, text)

### **5. Advanced Techniques: Support for Custom Context**

A powerful feature of `Trans-Hub` is the ability to pass a `context` dictionary in translation requests. To enable your engine to utilize this context, you need to do two things:

1. **Define a `ContextModel`**: In your engine file, create a Pydantic model that inherits from `BaseContextModel`, and define the fields you want to receive from the `context`.

    ```python
    # awesome_engine.py
    from trans_hub.engines.base import BaseContextModel

    class AwesomeEngineContext(BaseContextModel):
        # Allows users to specify the tone through context={"tone": "formal"}
        tone: Optional[str] = None

2. **Use `context_config` in `_atranslate_one`**: The base class will automatically validate `context` and pass the result as a dictionary to the `context_config` parameter. You only need to use it in your core logic.

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

### **6. A Complete Example: `AwesomeEngine`**

Below is a complete example of an `awesome_engine.py` file that follows all best practices. You can use this as a template to start your development.

```python
# trans_hub/engines/awesome_engine.py (完整示例)

import asyncio
from typing import Any, Optional

from pydantic_settings import BaseSettings

from trans_hub.engines.base import BaseEngineConfig, BaseTranslationEngine
from trans_hub.engines.meta import register_engine_config
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

# Assume there is a synchronous third-party library named 'awesome_sdk'
try:
    import awesome_sdk
except ImportError:
    awesome_sdk = None


# It seems there is no text provided for translation. Please provide the text you would like to have translated. 1. 定义配置模型 It seems there is no text provided for translation. Please provide the text you would like to have translated.
class AwesomeEngineConfig(BaseSettings, BaseEngineConfig):
    # BaseSettings 会自动从 .env 和环境变量加载 (前缀: TH_)
    awesome_api_key: str


# It seems there is no text provided for translation. Please provide the text you would like to have translated. 2. 定义引擎主类 It seems there is no text provided for translation. Please provide the text you would like to have translated.
class AwesomeEngine(BaseTranslationEngine[AwesomeEngineConfig]):
    CONFIG_MODEL = AwesomeEngineConfig
    VERSION = "1.0.0"

    def __init__(self, config: AwesomeEngineConfig):
        super().__init__(config)
        if awesome_sdk is None:
            raise ImportError("To use AwesomeEngine, please install the 'awesome-sdk' library")
        self.client = awesome_sdk.Client(api_key=config.awesome_api_key)

    def _translate_single_sync(self, text: str, target_lang: str) -> EngineBatchItemResult:
        """[Private] This is a synchronous method that performs blocking I/O."""
        try:
            translated_text = self.client.translate(text=text, target_language=target_lang)
            return EngineSuccess(translated_text=translated_text)
        except awesome_sdk.AuthError as e:
            return EngineError(error_message=f"Authentication error: {e}", is_retryable=False)
        except Exception as e:
            return EngineError(error_message=f"Unknown error: {e}", is_retryable=True)

    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[Implementation] Wrap synchronous call with asyncio.to_thread."""
        return await asyncio.to_thread(self._translate_single_sync, text, target_lang)


# It seems there is no text provided for translation. Please provide the text you would like to have translated. 3. 自我注册 It seems there is no text provided for translation. Please provide the text you would like to have translated.
# 将引擎名 "awesome" 与其配置模型 AwesomeEngineConfig 关联起来
register_engine_config("awesome", AwesomeEngineConfig)
```

### **7. Write Tests: Validate Your Engine**

It is crucial to write asynchronous tests for your engine. Since all business logic is driven by the `Coordinator`, testing whether the `Coordinator` can successfully use your new engine is the best method for integration testing.

```python
# tests/engines/test_awesome_engine.py
import pytest
from trans_hub.config import TransHubConfig
# ...

@pytest.mark.asyncio
async def test_coordinator_with_awesome_engine(monkeypatch, ...):
    # 1. Mock external dependencies
    # ...
    
    # 2. Set environment variables using monkeypatch
    monkeypatch.setenv("TH_AWESOME_API_KEY", "fake-key")

    # 3. Just activate the engine, and the configuration will be created and loaded automatically
    config = TransHubConfig(active_engine="awesome")
    
    # ... (subsequent Coordinator initialization and testing logic) ...
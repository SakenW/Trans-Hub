# **第三方引擎开发指南 - `Trans-Hub`**

欢迎你，未来的贡献者！本指南将带你一步步地为 `Trans-Hub` 开发一个全新的翻译引擎。得益于 `Trans-Hub` 的动态发现架构，这个过程比你想象的要简单得多。

## 目录

1.  [开发哲学：引擎的职责](#1-开发哲学引擎的职责)
2.  [准备工作：环境设置](#2-准备工作环境设置)
3.  [开发流程：三步完成一个新引擎](#3-开发流程三步完成一个新引擎)
    - [第一步：创建引擎文件](#第一步创建引擎文件)
    - [第二步：实现引擎代码](#第二步实现引擎代码)
    - [第三步：注册引擎配置](#第三步注册引擎配置)
4.  [编写测试：验证你的引擎](#4-编写测试验证你的引擎)
5.  [提交你的贡献](#5-提交你的贡献)
6.  [高级主题：处理上下文 (Context)](#6-高级主题处理上下文-context)
7.  [一份完整的示例：`AwesomeEngine`](#7-一份完整的示例awesomeengine)

---

### **1. 开发哲学：引擎的职责**

在 `Trans-Hub` 的架构中，一个 `Engine` 的职责被严格限定在：

- **接收一个字符串列表和目标语言**。
- **与一个特定的外部翻译 API 进行通信**。
- **正确地将 API 的成功和失败结果，包装成 `EngineSuccess` 或 `EngineError` 对象**。
- **返回一个结果列表**，其顺序和长度必须与输入完全对应。
- **通过 `EngineError` 的 `is_retryable` 属性，准确指示错误是否可重试**。

引擎**不需要**关心：

- 数据库操作
- 缓存命中/未命中逻辑
- **`business_id` 的关联、存储或持久化**
- **上下文哈希 (`context_hash`) 的生成** (这由 `trans_hub.utils.get_context_hash` 负责)
- 重试逻辑
- 速率限制
- 其他更高级的协调任务

所有这些复杂的任务都由 `Coordinator` 或 `PersistenceHandler` 来处理。你只需要专注于实现最纯粹、最高效的“翻译”这一步。

### **2. 准备工作：环境设置**

在开始之前，请确保你已经克隆了 `Trans-Hub` 的代码仓库，并设置好了本地开发环境。

```bash
# 1. 克隆仓库
git clone https://github.com/SakenW/trans-hub.git
cd trans-hub

# 2. 安装 Poetry (如果尚未安装)
# 参考 https://python-poetry.org/docs/#installation

# 3. 安装所有开发依赖
# 这将确保你有 pytest, black, ruff, mypy 等所有必要的代码质量工具
poetry install --with dev
```

### **3. 开发流程：三步完成一个新引擎**

假设我们要创建一个对接 “Awesome Translate” 服务的引擎。

#### **第一步：创建引擎文件**

在 `trans_hub/engines/` 目录下，为你的新引擎创建一个新的 Python 文件。文件名应该是小写的引擎名，例如 **`awesome_engine.py`**。

#### **第二步：实现引擎代码**

打开你刚创建的 `awesome_engine.py` 文件，编写引擎的核心逻辑。这通常包含以下几个部分：

1.  **必要的导入**: 导入 `typing` 相关类型，以及 `pydantic`, `pydantic_settings`。最重要的是，从 `trans_hub.engines.base` 导入 `BaseTranslationEngine`, `BaseEngineConfig`, `BaseContextModel`。
2.  **（可选）上下文模型**: 如果你的引擎需要额外的上下文信息（如语气、领域），请定义一个继承自 `BaseContextModel` 的 Pydantic 模型。**当 `Coordinator` 调用你的引擎的 `translate_batch` 方法时，它会确保传入的 `context` 参数是你的 `CONTEXT_MODEL` 的实例（或 `None`），而不是原始的字典。**
3.  **配置模型**: 定义一个继承自 **`pydantic_settings.BaseSettings` 和 `trans_hub.engines.base.BaseEngineConfig`** 的 Pydantic 模型。这是确保你的配置能从环境变量加载并与 `BaseTranslationEngine` 泛型兼容的关键。
4.  **引擎主类**: 实现你的引擎主类，它必须继承自 `BaseTranslationEngine` 并**明确指定泛型参数为你的配置模型**。

```python
# trans_hub/engines/awesome_engine.py

import logging # 用于日志记录
from typing import List, Optional, Dict, Any # 确保导入 Dict 和 Any (用于 context 参数类型)

# 导入 pydantic 相关
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict # 确保导入 SettingsConfigDict

# 导入 Trans-Hub 的基类和返回类型
from trans_hub.engines.base import BaseTranslationEngine, BaseEngineConfig, BaseContextModel
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

# 假设有一个 awesome-translate 的 SDK
# pip install awesome-sdk
try:
    import awesome_sdk
    # 假设 awesome_sdk.Client 是客户端类，awesome_sdk.AuthError 是其认证错误类型
    # 假设 awesome_sdk.ServiceError 是其服务错误类型
except ImportError:
    awesome_sdk = None
    logging.warning("awesome-sdk not found. AwesomeEngine will not be available.")

# 初始化模块日志记录器
logger = logging.getLogger(__name__)


# （可选）1. 定义 Context 模型 (如果引擎支持上下文信息)
# 这将确保从 Coordinator 传入的 context 是一个结构化的 Pydantic 对象
class AwesomeContext(BaseContextModel):
    """AwesomeTranslate 引擎的上下文模型。"""
    formality: str = "default"  # 例如，"default", "formal", "informal"


# 2. 定义配置模型
# 核心：同时继承 BaseSettings 和 BaseEngineConfig
class AwesomeEngineConfig(BaseSettings, BaseEngineConfig):
    """AwesomeTranslate 引擎的配置模型。"""
    model_config = SettingsConfigDict(
        extra="ignore"  # 忽略环境变量中未在模型中定义的额外字段
    )

    # 使用 validation_alias 来映射到 .env 文件中的环境变量
    api_key: str = Field(validation_alias='TH_AWESOME_API_KEY')
    # 可以为环境变量定义默认值
    region: str = Field(default='us-east-1', validation_alias='TH_AWESOME_REGION')


# 3. 实现引擎主类
# 核心：将 BaseTranslationEngine 泛型化为你定义的配置模型
class AwesomeEngine(BaseTranslationEngine[AwesomeEngineConfig]):
    """一个对接 AwesomeTranslate 服务的翻译引擎。"""

    # 将你的配置模型与引擎类绑定
    CONFIG_MODEL = AwesomeEngineConfig
    # （可选）绑定你的上下文模型，如果定义了的话
    CONTEXT_MODEL = AwesomeContext
    VERSION = "1.0.0" # 定义你的引擎版本
    REQUIRES_SOURCE_LANG = False # 如果你的引擎不强制要求提供源语言，则设置为 False

    def __init__(self, config: AwesomeEngineConfig):
        """
        初始化 AwesomeEngine 实例。
        Args:
            config: AwesomeEngineConfig 配置对象。
        """
        super().__init__(config)

        # 检查必要的依赖是否安装
        if awesome_sdk is None:
            raise ImportError(
                "要使用 AwesomeEngine，请先安装 'awesome-sdk' 库: pip install awesome-sdk"
            )

        # 验证关键配置项
        if not self.config.api_key:
            raise ValueError("AwesomeEngine requires an API key. Please set TH_AWESOME_API_KEY.")

        # 初始化与外部 API 通信所需的客户端
        self.client = awesome_sdk.Client(
            api_key=self.config.api_key,
            region=self.config.region # Mypy 现在知道 self.config 有 region 属性
        )
        logger.info(f"AwesomeEngine 初始化完成，使用区域: {self.config.region}")

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[AwesomeContext] = None, # <-- 注意这里 context 的类型是 AwesomeContext 实例
    ) -> List[EngineBatchItemResult]:
        """同步批量翻译文本。"""
        results: List[EngineBatchItemResult] = []

        # 从上下文对象中获取额外参数，如果定义了上下文模型的话
        formality_level = context.formality if context else "default"

        for text in texts:
            try:
                # 调用 SDK/API
                # 假设 SDK 支持 formality 参数
                api_response = self.client.translate(
                    text=text,
                    target_language=target_lang,
                    source_language=source_lang, # 传递源语言
                    formality=formality_level
                )
                # 将成功的响应包装成 EngineSuccess
                results.append(EngineSuccess(translated_text=api_response.translated_text))

            except awesome_sdk.AuthError as e:
                # 认证错误通常不可重试
                logger.error(f"AwesomeEngine Auth Error for text '{text}': {e}", exc_info=True)
                results.append(EngineError(error_message=f"认证错误: {e}", is_retryable=False))

            except awesome_sdk.ServiceError as e:
                # 服务端错误（如 5xx）通常可重试
                logger.error(f"AwesomeEngine Service Error for text '{text}': {e}", exc_info=True)
                results.append(EngineError(error_message=f"服务错误: {e}", is_retryable=True))

            except Exception as e:
                # 其他所有未预期错误，我们保守地假设为可重试的
                logger.error(f"AwesomeEngine Unexpected Error for text '{text}': {e}", exc_info=True)
                results.append(EngineError(error_message=f"未知错误: {e}", is_retryable=True))

        return results

    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[AwesomeContext] = None, # <-- 注意这里 context 的类型是 AwesomeContext 实例
    ) -> List[EngineBatchItemResult]:
        """异步批量翻译文本。

        强烈建议在这里实现真正的异步 API 调用（例如使用 `aiohttp` 或 SDK 的异步客户端），
        以避免在未来的异步工作流中阻塞事件循环。
        """
        logger.warning("AwesomeEngine 的异步版本尚未实现，将调用同步方法。这在生产环境中可能会阻塞事件循环。")
        # ⚠️ 注意: 在实际生产环境中，请实现真正的异步逻辑，例如：
        # async_results = []
        # for text in texts:
        #     try:
        #         translated_text = await self.client.atranslate(text, target_language=target_lang, source_language=source_lang, formality=context.formality if context else "default")
        #         async_results.append(EngineSuccess(translated_text=translated_text))
        #     except Exception as e:
        #         async_results.append(EngineError(error_message=str(e), is_retryable=True))
        # return async_results

        # 当前仅为示例，直接调用同步方法
        return self.translate_batch(texts, target_lang, source_lang, context)

```

#### **第三步：注册引擎配置**

这是最后一步，也是最简单的一步。为了让 `Coordinator` 能够为你的引擎创建和传递配置，你需要在 `trans_hub/config.py` 中“注册”你的配置模型。

打开 `trans_hub/config.py` 文件，在 `EngineConfigs` 模型中添加你的引擎配置。

```python
# trans_hub/config.py

from typing import Optional # 确保 Optional 已导入
from pydantic import BaseModel # 确保 BaseModel 已导入

# 1. 导入你的新配置模型
from trans_hub.engines.awesome_engine import AwesomeEngineConfig
# ... 可能还有其他引擎配置的导入

class EngineConfigs(BaseModel):
    """所有引擎配置的聚合模型。"""
    # ... 其他引擎配置 ...

    # 2. 在这里添加你的新引擎配置字段
    # 字段名必须是小写的引擎名，且与 TH_ACTIVE_ENGINE 中使用的名称一致 (例如 "awesome")
    awesome: Optional[AwesomeEngineConfig] = None # 注意这里是 Optional，表示该引擎配置是可选的
```

**完成了！** `engine_registry` 会在你下次运行程序时自动发现并加载你的 `AwesomeEngine`。用户只需在他们的 `.env` 文件中配置 `TH_ACTIVE_ENGINE="awesome"` 并提供相应的 `TH_AWESOME_API_KEY` 等环境变量，即可使用你的引擎。

### **4. 编写测试：验证你的引擎**

为了确保你的引擎能够稳定工作，并能被我们的测试套件覆盖，请更新 `run_coordinator_test.py`。

1.  在文件顶部导入你的新引擎：`from trans_hub.engines.awesome_engine import AwesomeEngine, AwesomeEngineConfig, AwesomeContext`。
2.  仿照 `test_openai_engine_flow`，创建一个新的测试函数 `test_awesome_engine_flow`。
3.  在这个新函数中，创建 `TransHubConfig` 时，将 `active_engine` 设置为 `"awesome"`，并在 `engine_configs` 中提供 `AwesomeEngineConfig` 的实例。
4.  在 `main` 函数中调用你的新测试函数。

例如：

```python
# run_coordinator_test.py 示例片段

# ... 其他导入 ...
from trans_hub.engines.awesome_engine import AwesomeEngine, AwesomeEngineConfig, AwesomeContext
from trans_hub.utils import get_context_hash # 导入 get_context_hash

# ...

def test_awesome_engine_flow():
    """测试 AwesomeEngine 翻译流程。"""
    logger.info("--- 开始测试 AwesomeEngine 翻译流程 ---")

    # 假设你的 .env 文件中有 TH_AWESOME_API_KEY 和 TH_AWESOME_REGION
    # 加载 .env 文件（确保在程序入口处调用）
    dotenv.load_dotenv()

    # 创建 TransHubConfig 实例，指定 AwesomeEngine
    config = TransHubConfig(
        active_engine="awesome",
        engine_configs=EngineConfigs(
            awesome=AwesomeEngineConfig(
                api_key="YOUR_AWESOME_API_KEY_HERE", # 在测试环境中替换为真实的测试key
                region="us-east-1"
            )
        )
    )

    # 模拟持久化处理器（可使用内存实现或 Mock）
    mock_persistence_handler = MockPersistenceHandler()

    coordinator = Coordinator(
        config=config,
        persistence_handler=mock_persistence_handler
    )

    test_text = "Hello, world!"
    business_id = "test.awesome.greeting"
    target_lang = "zh-CN"
    # 示例上下文：创建 AwesomeContext 实例，然后转换为字典传入 request
    context_data_instance = AwesomeContext(formality="formal")
    context_data_dict = context_data_instance.model_dump() # 将 Pydantic 模型转换为字典传入 request

    # 发送翻译请求
    coordinator.request(
        target_langs=[target_lang],
        text_content=test_text,
        business_id=business_id,
        context=context_data_dict # 将 Pydantic 模型转换为字典传入
    )

    # 处理待翻译任务
    translation_results = list(coordinator.process_pending_translations(target_lang=target_lang))

    assert len(translation_results) == 1
    result = translation_results[0]
    assert result.status == TranslationStatus.TRANSLATED
    assert result.translated_content # 检查翻译结果非空
    assert result.engine == "awesome" # 确保使用了你的引擎
    assert result.business_id == business_id # 确保 business_id 被正确关联
    assert result.context_hash == get_context_hash(context_data_dict) # 确保 context_hash 正确

    logger.info(f"AwesomeEngine 翻译结果: {result.translated_content}")

    # 清理（可选，取决于 MockPersistenceHandler）
    coordinator.close()
    logger.info("--- AwesomeEngine 翻译流程测试结束 ---")

# 在 main 函数中调用
if __name__ == "__main__":
    setup_logging(log_level="DEBUG", log_format="console")
    test_awesome_engine_flow()
    # ... 其他测试函数
```

### **5. 提交你的贡献**

当你完成了以上所有步骤，并确保所有测试都能通过时，你就可以提交一个 Pull Request 到我们的主仓库了！请在 PR 中简要说明你的新引擎的功能和用法。

感谢你为 `Trans-Hub` 生态系统做出贡献！

### **6. 高级主题：处理上下文 (Context)**

如果你的引擎支持更高级的功能（比如术语表、正式/非正式语气等），你可以通过 `Context` 机制来实现。

1.  **定义 Context 模型**: 在你的引擎文件中，创建一个继承自 `BaseContextModel` 的 Pydantic 模型。

    ```python
    # your_engine.py
    from trans_hub.engines.base import BaseContextModel
    from pydantic import Field # 如果需要 Field

    class YourContext(BaseContextModel):
        formality: str = Field(default="default", description="翻译的正式程度")
        # ... 其他自定义上下文字段
    ```

2.  **绑定到引擎**: 在你的引擎类中，指定 `CONTEXT_MODEL`。
    ```python
    # your_engine.py
    class YourEngine(BaseTranslationEngine[YourEngineConfig]): # 记住泛型参数
        CONTEXT_MODEL = YourContext # 绑定你的 Context 模型
        # ...
    ```
3.  **在 `translate_batch` 中使用**: 当上层应用通过 `coordinator.request(..., context={'formality': 'formal'})` 传入一个字典时，`Coordinator` 会自动使用你的引擎的 `CONTEXT_MODEL` (`YourContext`) 来验证这个字典，并将其转换为 `YourContext` 的实例，然后传递给 `translate_batch` 或 `atranslate_batch` 方法。

    ```python
    # your_engine.py
    from typing import Optional, Dict, Any # 确保 Optional, Dict, Any 已导入
    # ...

    # 明确 context 的类型为 YourContext 实例
    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[YourContext] = None # <-- 这里的 context 已是 YourContext 实例
    ) -> List[EngineBatchItemResult]:
        formality = "default"
        if context:
            formality = context.formality # Mypy 现在会识别 context 为 YourContext 类型，可以直接访问其属性
        # 使用 formality 值来调用 API
        api_response = self.client.translate(..., formality=formality)
        # ...
    ```

### **7. 一份完整的示例：`AwesomeEngine`**

```python
# trans_hub/engines/awesome_engine.py (完整示例)

import logging
from typing import List, Optional, Dict, Any # 确保导入 Dict 和 Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.engines.base import BaseTranslationEngine, BaseEngineConfig, BaseContextModel
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

# 假设 awesome_sdk 是第三方库
try:
    import awesome_sdk
except ImportError:
    awesome_sdk = None

logger = logging.getLogger(__name__)


# 1. 上下文模型 (如果你的引擎支持，例如，定义翻译的语气)
class AwesomeContext(BaseContextModel):
    formality: str = Field(default="default", description="翻译的正式程度，如 'default', 'formal', 'informal'")


# 2. 配置模型
# 核心：同时继承 BaseSettings 和 BaseEngineConfig
class AwesomeEngineConfig(BaseSettings, BaseEngineConfig):
    model_config = SettingsConfigDict(
        extra="ignore"
    )
    api_key: str = Field(validation_alias='TH_AWESOME_API_KEY')
    region: str = Field(default='us-east-1', validation_alias='TH_AWESOME_REGION')


# 3. 引擎主类
# 核心：指定泛型参数为 AwesomeEngineConfig
class AwesomeEngine(BaseTranslationEngine[AwesomeEngineConfig]):
    CONFIG_MODEL = AwesomeEngineConfig
    CONTEXT_MODEL = AwesomeContext # 绑定上下文模型 (如果定义了)
    VERSION = "1.0.0"
    REQUIRES_SOURCE_LANG = False # 假设 AwesomeEngine 可以自动检测源语言

    def __init__(self, config: AwesomeEngineConfig):
        """
        初始化 AwesomeEngine 实例。
        Args:
            config: AwesomeEngineConfig 配置对象。
        """
        super().__init__(config)

        if awesome_sdk is None:
            raise ImportError(
                "要使用 AwesomeEngine，请先安装 'awesome-sdk' 库: pip install awesome-sdk"
            )
        if not self.config.api_key:
            raise ValueError("AwesomeEngine requires an API key. Please set TH_AWESOME_API_KEY.")

        # 初始化第三方 SDK 客户端
        self.client = awesome_sdk.Client(api_key=self.config.api_key, region=self.config.region)
        logger.info(f"AwesomeEngine 初始化完成，使用区域: {self.config.region}")

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[AwesomeContext] = None, # 明确上下文类型
    ) -> List[EngineBatchItemResult]:
        """同步批量翻译。"""
        results: List[EngineBatchItemResult] = []

        formality_level = context.formality if context else "default" # 从上下文对象中获取正式程度

        for text in texts:
            try:
                # 假设 SDK 的同步翻译方法
                translated_text = self.client.translate(
                    text=text,
                    target_language=target_lang,
                    source_language=source_lang,
                    formality=formality_level
                )
                results.append(EngineSuccess(translated_text=translated_text))
            except awesome_sdk.AuthError as e:
                logger.error(f"AwesomeEngine Auth Error for text '{text}': {e}", exc_info=True)
                results.append(EngineError(error_message=f"认证错误: {e}", is_retryable=False))
            except awesome_sdk.ServiceError as e:
                logger.error(f"AwesomeEngine Service Error for text '{text}': {e}", exc_info=True)
                results.append(EngineError(error_message=f"服务错误: {e}", is_retryable=True))
            except Exception as e:
                logger.error(f"AwesomeEngine Unexpected Error for text '{text}': {e}", exc_info=True)
                results.append(EngineError(error_message=f"未知错误: {e}", is_retryable=True))

        return results

    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[AwesomeContext] = None, # 明确上下文类型
    ) -> List[EngineBatchItemResult]:
        """异步批量翻译。

        强烈建议在这里实现真正的异步 API 调用，以避免阻塞事件循环。
        """
        results: List[EngineBatchItemResult] = []

        formality_level = context.formality if context else "default"

        for text in texts:
            try:
                # 假设 SDK 的异步翻译方法
                # translated_text = await self.client.atranslate(
                #     text=text,
                #     target_language=target_lang,
                #     source_language=source_lang,
                #     formality=formality_level
                # )
                # 这里为了示例，暂时调用同步方法
                translated_text = self.client.translate(
                    text=text,
                    target_language=target_lang,
                    source_language=source_lang,
                    formality=formality_level
                )
                results.append(EngineSuccess(translated_text=translated_text))
            except awesome_sdk.AuthError as e:
                logger.error(f"AwesomeEngine Auth Error (Async) for text '{text}': {e}", exc_info=True)
                results.append(EngineError(error_message=f"认证错误: {e}", is_retryable=False))
            except awesome_sdk.ServiceError as e:
                logger.error(f"AwesomeEngine Service Error (Async) for text '{text}': {e}", exc_info=True)
                results.append(EngineError(error_message=f"服务错误: {e}", is_retryable=True))
            except Exception as e:
                logger.error(f"AwesomeEngine Unexpected Error (Async) for text '{text}': {e}", exc_info=True)
                results.append(EngineError(error_message=f"未知错误: {e}", is_retryable=True))

        return results
```

---

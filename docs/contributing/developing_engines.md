# 指南：开发第三方引擎

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
- **同步/异步的协调** (这由 `Coordinator` 负责，它会智能地调用 `translate_batch` 或 `atranslate_batch`)

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
# 这将确保你有 pytest, ruff, mypy 等所有必要的代码质量工具
poetry install --with dev
```

### **3. 开发流程：三步完成一个新引擎**

假设我们要创建一个对接 “Awesome Translate” 服务的引擎。

#### **第一步：创建引擎文件**

在 `trans_hub/engines/` 目录下，为你的新引擎创建一个新的 Python 文件。文件名应该是小写的引擎名，例如 **`awesome_engine.py`**。

#### **第二步：实现引擎代码**

打开你刚创建的 `awesome_engine.py` 文件，编写引擎的核心逻辑。这通常包含以下几个部分：

1.  **必要的导入**: 导入 `typing` 相关类型，以及 `pydantic`, `pydantic_settings`。最重要的是，从 `trans_hub.engines.base` 导入 `BaseTranslationEngine`, `BaseEngineConfig`, `BaseContextModel`，并从 `trans_hub.types` 导入核心结果类型。
2.  **（可选）上下文模型**: 如果你的引擎需要额外的上下文信息（如语气、领域），请定义一个继承自 `BaseContextModel` 的 Pydantic 模型。
3.  **配置模型**: 定义一个继承自 `pydantic_settings.BaseSettings` 和 `trans_hub.engines.base.BaseEngineConfig` 的 Pydantic 模型。
4.  **引擎主类**: 实现你的引擎主类，它必须继承自 `BaseTranslationEngine`。

> ⚠️ **重要提示：`EngineError` 的正确使用**
>
> 当你的引擎在与外部 API 通信时遇到错误（例如认证失败、服务不可用），你**不应该** `raise EngineError(...)`。
>
> 正确的做法是，将 `EngineError` 对象作为结果列表的一项 **`return`** 回去。
>
> ```python
> # 正确做法
> from trans_hub.types import EngineSuccess, EngineError
>
> def translate_batch(...):
>     results = []
>     try:
>         # ... api call ...
>         results.append(EngineSuccess(...))
>     except SomeAuthError as e:
>         # 返回 EngineError 对象
>         results.append(EngineError(error_message=str(e), is_retryable=False))
>     return results
> ```
>
> 这是因为 `EngineError` 是一个 Pydantic 模型，而不是一个异常类。直接抛出它会导致 `TypeError: exceptions must derive from BaseException`。`Coordinator` 期望收到一个与输入列表长度完全对应的结果列表，其中失败的项由 `EngineError` 对象表示。

#### **第三步：注册引擎配置**

这是最后一步，也是最简单的一步。为了让 `Coordinator` 能够为你的引擎创建和传递配置，你需要在 `trans_hub/config.py` 中“注册”你的配置模型。

打开 `trans_hub/config.py` 文件，在 `EngineConfigs` 模型中添加你的引擎配置。

```python
# trans_hub/config.py

from typing import Optional
from pydantic import BaseModel

# 1. 导入你的新配置模型
from trans_hub.engines.awesome_engine import AwesomeEngineConfig
# ... 可能还有其他引擎配置的导入

class EngineConfigs(BaseModel):
    """所有引擎配置的聚合模型。"""
    # ... 其他引擎配置 ...

    # 2. 在这里添加你的新引擎配置字段
    # 字段名必须是小写的引擎名，且与 TH_ACTIVE_ENGINE 中使用的名称一致 (例如 "awesome")
    awesome: Optional[AwesomeEngineConfig] = None
```

**完成了！** `engine_registry` 会在你下次运行程序时自动发现并加载你的 `AwesomeEngine`。用户只需在他们的 `.env` 文件中配置 `TH_ACTIVE_ENGINE="awesome"` 并提供相应的 `TH_AWESOME_API_KEY` 等环境变量，即可使用你的引擎。

### **4. 编写测试：验证你的引擎**

为了确保你的引擎能够稳定工作，并能被我们的测试套件覆盖，你应该为它编写测试。一个好的测试至少应该验证：

1.  引擎在给定有效输入时，能返回正确的 `EngineSuccess` 结果。
2.  引擎能正确处理 API 错误，并返回相应的 `EngineError` 对象。
3.  `Coordinator` 能够正确加载和驱动你的引擎。

<!-- 修改点：添加了一段解释，说明为什么在测试中手动创建配置实例。 -->

在单元测试中，我们推荐手动创建配置实例并传入明确的值（如 `"fake-key"`），而不是依赖于 `.env` 文件。这遵循了测试的“隔离性”原则，确保测试不依赖于外部环境，从而使测试结果更加稳定和可预测。

以下是一个使用 `pytest` 和 `pytest-mock` 的测试示例，你可以将其添加到项目的测试套件中。

```python
# tests/test_awesome_engine.py (测试示例)
import pytest
from unittest.mock import MagicMock, patch

from trans_hub.config import TransHubConfig, EngineConfigs
from trans_hub.coordinator import Coordinator
from trans_hub.engines.awesome_engine import AwesomeEngineConfig
from trans_hub.persistence import DefaultPersistenceHandler # 或者一个模拟的持久化处理器
from trans_hub.types import TranslationStatus, ContentItem

@pytest.fixture
def mock_persistence_handler():
    """创建一个模拟的持久化处理器。"""
    handler = MagicMock(spec=DefaultPersistenceHandler)
    mock_item = ContentItem(
        content_id=1, value="Hello, world!", context_hash="__GLOBAL__", context={}
    )
    handler.stream_translatable_items.return_value = [[mock_item]]
    handler.get_business_id_for_content.return_value = "test.greeting"
    return handler

# 使用 patch 来模拟外部 awesome_sdk 库
@patch('trans_hub.engines.awesome_engine.awesome_sdk')
def test_coordinator_with_awesome_engine(mock_sdk, mock_persistence_handler):
    """测试 Coordinator 是否能成功驱动 AwesomeEngine 并获得正确结果。"""
    # 1. 模拟 SDK 的行为
    mock_client = MagicMock()
    mock_client.translate.return_value.translated_text = "你好，世界！"
    mock_sdk.Client.return_value = mock_client

    # 2. 配置 Trans-Hub 以使用 AwesomeEngine
    config = TransHubConfig(
        active_engine="awesome",
        engine_configs=EngineConfigs(
            awesome=AwesomeEngineConfig(awesome_api_key="fake-key", awesome_region="test-region")
        )
    )
    coordinator = Coordinator(config=config, persistence_handler=mock_persistence_handler)

    # 3. 执行翻译流程
    results = list(coordinator.process_pending_translations(target_lang="zh-CN"))

    # 4. 断言结果
    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.TRANSLATED
    assert result.translated_content == "你好，世界！"
    assert result.engine == "awesome"
    assert result.business_id == "test.greeting"

    # 5. 确认外部 SDK 被正确调用
    # 这里的参数名 (api_key, region) 必须匹配外部 awesome_sdk.Client 的 API，而不是我们内部的字段名
    mock_sdk.Client.assert_called_once_with(api_key="fake-key", region="test-region")
    mock_client.translate.assert_called_once()
```

### **5. 提交你的贡献**

当你完成了以上所有步骤，并确保所有测试都能通过时，你就可以提交一个 Pull Request 到我们的主仓库了！请在 PR 中简要说明你的新引擎的功能、用法，以及你所做的测试。我们非常感谢社区的每一份贡献，它让 `Trans-Hub` 变得更好。

### **6. 高级主题：处理上下文 (Context)**

如果你的引擎支持更高级的功能（比如术语表、正式/非正式语气等），你可以通过 `Context` 机制来实现。

1.  **定义 Context 模型**: 在你的引擎文件中，创建一个继承自 `BaseContextModel` 的 Pydantic 模型。
2.  **绑定到引擎**: 在你的引擎类中，指定 `CONTEXT_MODEL`。
3.  **在 `translate_batch` 中使用**: 当上层应用通过 `coordinator.request(..., context={'formality': 'formal'})` 传入一个字典时，`Coordinator` 会自动使用你的引擎的 `CONTEXT_MODEL` (`YourContext`) 来验证这个字典，并将其转换为 `YourContext` 的实例，然后传递给 `translate_batch` 或 `atranslate_batch` 方法。

    ```python
    # your_engine.py
    from typing import Optional, List
    from trans_hub.types import EngineBatchItemResult
    from .base import BaseContextModel, BaseTranslationEngine

    class YourContext(BaseContextModel):
        formality: str = "default"

    # 在引擎方法中明确 context 的类型为 YourContext 实例
    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[YourContext] = None # <-- 这里的 context 已是 YourContext 实例
    ) -> List[EngineBatchItemResult]:
        formality = "default"
        if context:
            # 你现在可以安全地访问其属性，Mypy 会进行类型检查
            formality = context.formality
        # 使用 formality 值来调用 API
        # api_response = self.client.translate(..., formality=formality)
        # ...
    ```

### **7. 一份完整的示例：`AwesomeEngine`**

下面是一个完整的、可直接使用的 `awesome_engine.py` 文件示例，它包含了上下文模型、配置模型和引擎主类的完整实现。**此示例已更新，以遵循避免 `mypy` 错误的最佳实践。**

```python
# trans_hub/engines/awesome_engine.py (完整示例)

import logging
# <!-- 修改点：添加了 List 的导入 -->
from typing import List, Optional

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
class AwesomeEngineConfig(BaseSettings, BaseEngineConfig):
    """
    AwesomeEngine 的配置。
    最佳实践：字段名直接对应环境变量（去除 'TH_' 前缀），以避免 mypy 静态分析问题。
    """
    model_config = SettingsConfigDict(
        env_prefix="TH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # 字段名直接对应环境变量 TH_AWESOME_API_KEY
    awesome_api_key: str
    # 字段名直接对应环境变量 TH_AWESOME_REGION
    awesome_region: str = 'us-east-1'


# 3. 引擎主类
class AwesomeEngine(BaseTranslationEngine[AwesomeEngineConfig]):
    CONFIG_MODEL = AwesomeEngineConfig
    CONTEXT_MODEL = AwesomeContext # 绑定上下文模型
    VERSION = "1.0.0"
    REQUIRES_SOURCE_LANG = False
    IS_ASYNC_ONLY = False # 这是一个同步引擎

    def __init__(self, config: AwesomeEngineConfig):
        """初始化 AwesomeEngine 实例。"""
        super().__init__(config)
        if awesome_sdk is None:
            raise ImportError("要使用 AwesomeEngine，请先安装 'awesome-sdk' 库")

        # Pydantic 已经保证了 awesome_api_key 的存在，所以无需额外检查

        # <!-- 修改点：添加了注释，解释内部字段名和外部 SDK 参数名的映射关系 -->
        # 使用更新后的字段名访问配置。
        # 注意：我们将内部配置字段 (self.config.awesome_api_key) 的值，
        # 传递给外部 awesome_sdk.Client 所期望的参数 (api_key)。
        # 这种映射是引擎开发者的核心职责之一。
        self.client = awesome_sdk.Client(
            api_key=self.config.awesome_api_key,
            region=self.config.awesome_region
        )
        logger.info(f"AwesomeEngine 初始化完成，使用区域: {self.config.awesome_region}")

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[AwesomeContext] = None,
    ) -> List[EngineBatchItemResult]:
        """同步批量翻译。"""
        results: List[EngineBatchItemResult] = []
        formality_level = context.formality if context else "default"
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
                logger.error(f"AwesomeEngine 认证错误 for text '{text}': {e}", exc_info=True)
                results.append(EngineError(error_message=f"认证错误: {e}", is_retryable=False))
            except awesome_sdk.ServiceError as e:
                logger.error(f"AwesomeEngine 服务错误 for text '{text}': {e}", exc_info=True)
                results.append(EngineError(error_message=f"服务错误: {e}", is_retryable=True))
            except Exception as e:
                logger.error(f"AwesomeEngine 未知错误 for text '{text}': {e}", exc_info=True)
                results.append(EngineError(error_message=f"未知错误: {e}", is_retryable=True))
        return results

    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[AwesomeContext] = None,
    ) -> List[EngineBatchItemResult]:
        """异步批量翻译。

        因为这是一个同步引擎，我们在这里只是简单地调用同步版本。
        在真正的异步引擎中，这里应该使用异步客户端（如 aiohttp）进行非阻塞的 API 调用。
        """
        logger.warning("AwesomeEngine 的异步版本尚未实现，将回退到同步方法。")
        return self.translate_batch(texts, target_lang, source_lang, context)
```

# **第三方引擎开发指南 - `Trans-Hub`**

欢迎你，未来的贡献者！本指南将带你一步步地为 `Trans-Hub` 开发一个全新的翻译引擎。得益于 `Trans-Hub` 的动态发现架构，这个过程比你想象的要简单得多。

## 目录
1.  [开发哲学：引擎的职责](#1-开发哲学引擎的职责)
2.  [准备工作：环境设置](#2-准备工作环境设置)
3.  [开发流程：三步完成一个新引擎](#3-开发流程三步完成一个新引擎)
    *   [第一步：创建引擎文件](#第一步创建引擎文件)
    *   [第二步：实现引擎代码](#第二步实现引擎代码)
    *   [第三步：注册引擎配置](#第三步注册引擎配置)
4.  [编写测试：验证你的引擎](#4-编写测试验证你的引擎)
5.  [提交你的贡献](#5-提交你的贡献)
6.  [高级主题：处理上下文 (Context)](#6-高级主题处理上下文-context)
7.  [一份完整的示例：`AwesomeEngine`](#7-一份完整的示例awesomeengine)

---

### **1. 开发哲学：引擎的职责**

在 `Trans-Hub` 的架构中，一个 `Engine` 的职责被严格限定在：

*   **接收一个字符串列表和目标语言**。
*   **与一个特定的外部翻译 API 进行通信**。
*   **返回一个结果列表**，其顺序和长度必须与输入完全对应。
*   **正确地将 API 的成功和失败结果，包装成 `EngineSuccess` 或 `EngineError` 对象**。

引擎**不需要**关心：
*   数据库操作
*   缓存
*   重试逻辑
*   速率限制

所有这些复杂的任务都由 `Coordinator` 来处理。你只需要专注于实现最纯粹的“翻译”这一步。

### **2. 准备工作：环境设置**

在开始之前，请确保你已经克隆了 `Trans-Hub` 的代码仓库，并设置好了本地开发环境。

```bash
# 1. 克隆仓库
git clone https://github.com/SakenW/trans-hub.git
cd trans-hub

# 2. 安装 Poetry (如果尚未安装)
# 参考 https://python-poetry.org/docs/#installation

# 3. 安装所有开发依赖
# 这将确保你有 pytest, black, ruff 等所有必要的工具
poetry install --with dev
```

### **3. 开发流程：三步完成一个新引擎**

假设我们要创建一个对接 “Awesome Translate” 服务的引擎。

#### **第一步：创建引擎文件**

在 `trans_hub/engines/` 目录下，为你的新引擎创建一个新的 Python 文件。文件名应该是小写的引擎名，例如 **`awesome_engine.py`**。

#### **第二步：实现引擎代码**

打开你刚创建的 `awesome_engine.py` 文件，编写引擎的核心逻辑。这通常包含两个部分：一个**配置模型**和一个**引擎主类**。

```python
# trans_hub/engines/awesome_engine.py

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings

# 导入 Trans-Hub 的基类和返回类型
from trans_hub.engines.base import BaseTranslationEngine, BaseEngineConfig, BaseContextModel
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

# 假设有一个 awesome-translate 的 SDK
import awesome_sdk

# 1. 定义配置模型
class AwesomeEngineConfig(BaseSettings):
    """AwesomeTranslate 引擎的配置模型。"""
    # 使用 validation_alias 来映射到 .env 文件中的环境变量
    api_key: str = Field(validation_alias='TH_AWESOME_API_KEY')
    region: str = Field(default='us-east-1', validation_alias='TH_AWESOME_REGION')

# 2. 实现引擎主类
class AwesomeEngine(BaseTranslationEngine):
    """一个对接 AwesomeTranslate 服务的翻译引擎。"""
    
    # 将你的配置模型与引擎类绑定
    CONFIG_MODEL = AwesomeEngineConfig
    VERSION = "1.0.0" # 定义你的引擎版本

    def __init__(self, config: AwesomeEngineConfig):
        super().__init__(config)
        # 初始化与外部 API 通信所需的客户端
        self.client = awesome_sdk.Client(
            api_key=self.config.api_key,
            region=self.config.region
        )

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        
        results: List[EngineBatchItemResult] = []
        for text in texts:
            try:
                # 调用 SDK/API
                api_response = self.client.translate(text=text, target=target_lang)
                # 将成功的响应包装成 EngineSuccess
                results.append(EngineSuccess(translated_text=api_response.translated_text))
                
            except awesome_sdk.AuthError as e:
                # 这是一个不可重试的错误（API Key 错误）
                results.append(EngineError(error_message=str(e), is_retryable=False))
                
            except Exception as e:
                # 其他所有错误，我们保守地假设为可重试的
                results.append(EngineError(error_message=str(e), is_retryable=True))
                
        return results

    async def atranslate_batch(
        self, texts: List[str], target_lang: str,
        # ...
    ) -> List[EngineBatchItemResult]:
        raise NotImplementedError("AwesomeEngine 的异步版本尚未实现。")
```

#### **第三步：注册引擎配置**

这是最后一步，也是最简单的一步。为了让 `Coordinator` 能够为你的引擎创建和传递配置，你需要在 `trans_hub/config.py` 中“注册”你的配置模型。

打开 `trans_hub/config.py` 文件，在 `EngineConfigs` 模型中添加你的引擎配置。

```python
# trans_hub/config.py

# 1. 导入你的新配置模型
from trans_hub.engines.awesome_engine import AwesomeEngineConfig
# ...

class EngineConfigs(BaseModel):
    # ... 其他引擎配置 ...
    
    # 2. 在这里添加你的新引擎配置字段
    # 字段名必须是小写的引擎名，与注册表中的 key 一致 (awesome)
    awesome: Optional[AwesomeEngineConfig] = None
```

**完成了！** `engine_registry` 会在你下次运行程序时自动发现并加载你的 `AwesomeEngine`。

### **4. 编写测试：验证你的引擎**

为了确保你的引擎能够稳定工作，并能被我们的测试套件覆盖，请更新 `run_coordinator_test.py`。

1.  在文件顶部导入你的新引擎：`from trans_hub.engines.awesome_engine import AwesomeEngine, AwesomeEngineConfig`。
2.  仿照 `test_openai_engine_flow`，创建一个新的测试函数 `test_awesome_engine_flow`。
3.  在这个新函数中，创建 `TransHubConfig` 时，将 `active_engine` 设置为 `"awesome"`，并在 `engine_configs` 中提供 `AwesomeEngineConfig` 的实例。
4.  在 `main` 函数中调用你的新测试函数。

### **5. 提交你的贡献**

当你完成了以上所有步骤，并确保所有测试都能通过时，你就可以提交一个 Pull Request 到我们的主仓库了！请在 PR 中简要说明你的新引擎的功能和用法。

感谢你为 `Trans-Hub` 生态系统做出贡献！

### **6. 高级主题：处理上下文 (Context)**

如果你的引擎支持更高级的功能（比如术语表、正式/非正式语气等），你可以通过 `Context` 机制来实现。

1.  **定义 Context 模型**: 在你的引擎文件中，创建一个继承自 `BaseContextModel` 的 Pydantic 模型。
    ```python
    # awesome_engine.py
    from trans_hub.engines.base import BaseContextModel
    
    class AwesomeContext(BaseContextModel):
        formality: str = "default" # e.g., "default", "formal", "informal"
    ```
2.  **绑定到引擎**: 在你的引擎类中，指定 `CONTEXT_MODEL`。
    ```python
    # awesome_engine.py
    class AwesomeEngine(BaseTranslationEngine):
        CONTEXT_MODEL = AwesomeContext # 绑定你的 Context 模型
        # ...
    ```
3.  **在 `translate_batch` 中使用**: `Coordinator` 会自动验证并传入正确的 `context` 对象。
    ```python
    # awesome_engine.py
    def translate_batch(self, ..., context: Optional[AwesomeContext] = None):
        formality = "default"
        if context:
            formality = context.formality
        # 使用 formality 值来调用 API
        api_response = self.client.translate(..., formality=formality)
        # ...
    ```
---

### **7. 一份完整的示例：`AwesomeEngine`**
(本节内容与第3、6节合并，提供一个完整的最终文件示例)

```python
# trans_hub/engines/awesome_engine.py (完整示例)

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from trans_hub.engines.base import BaseTranslationEngine, BaseEngineConfig, BaseContextModel
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess
import awesome_sdk # 假设的 SDK

# 1. 上下文模型 (如果需要)
class AwesomeContext(BaseContextModel):
    formality: str = "default"

# 2. 配置模型
class AwesomeEngineConfig(BaseSettings):
    api_key: str = Field(validation_alias='TH_AWESOME_API_KEY')
    region: str = Field(default='us-east-1', validation_alias='TH_AWESOME_REGION')

# 3. 引擎主类
class AwesomeEngine(BaseTranslationEngine):
    CONFIG_MODEL = AwesomeEngineConfig
    CONTEXT_MODEL = AwesomeContext # 绑定上下文模型
    VERSION = "1.0.0"

    def __init__(self, config: AwesomeEngineConfig):
        super().__init__(config)
        self.client = awesome_sdk.Client(api_key=config.api_key, region=config.region)

    def translate_batch(
        self, texts: List[str], target_lang: str,
        source_lang: Optional[str] = None, context: Optional[AwesomeContext] = None,
    ) -> List[EngineBatchItemResult]:
        
        formality_level = context.formality if context else "default"
        
        results: List[EngineBatchItemResult] = []
        for text in texts:
            try:
                api_response = self.client.translate(
                    text=text, target=target_lang, source=source_lang, formality=formality_level
                )
                results.append(EngineSuccess(translated_text=api_response.translated_text))
            except awesome_sdk.AuthError as e:
                results.append(EngineError(error_message=str(e), is_retryable=False))
            except Exception as e:
                results.append(EngineError(error_message=str(e), is_retryable=True))
                
        return results

    async def atranslate_batch(self, ...):
        raise NotImplementedError
```
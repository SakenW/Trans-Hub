# 第三方引擎开发指南 - `Trans-Hub`

欢迎你，未来的贡献者！本指南将带你一步步地为 `Trans-Hub` 开发一个全新的翻译引擎。我们致力于让这个过程尽可能简单、直接。

## 目录
1.  [开发哲学：引擎的职责](#1-开发哲学引擎的职责)
2.  [准备工作：环境设置](#2-准备工作环境设置)
3.  [第一步：创建引擎文件](#3-第一步创建引擎文件)
4.  [第二步：定义配置模型](#4-第二步定义配置模型)
5.  [第三步：实现引擎主类](#5-第三步实现引擎主类)
6.  [第四步：注册你的引擎](#6-第四步注册你的引擎)
7.  [第五步：编写测试](#7-第五步编写测试)
8.  [提交你的贡献](#8-提交你的贡献)
9.  [高级主题：处理上下文 (Context)](#9-高级主题处理上下文-context)

---

### **1. 开发哲学：引擎的职责**

在 `Trans-Hub` 的架构中，一个 `Engine` 的职责被严格限定在：

*   **接收一个字符串列表和目标语言**。
*   **与一个特定的外部翻译 API 进行通信**。
*   **返回一个结果列表**，其顺序和长度与输入完全对应。
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
# 克隆仓库
git clone https://github.com/SakenW/trans-hub.git
cd trans-hub

# 使用 Poetry 安装所有开发依赖
# 这将确保你有 pytest, black, ruff 等所有必要的工具
poetry install --with dev
```

### **3. 第一步：创建引擎文件**

在 `trans_hub/engines/` 目录下，为你的新引擎创建一个新的 Python 文件。文件名应该是小写的引擎名，例如 `deepl.py` 或 `google.py`。

假设我们要创建一个对接 “Awesome Translate” 服务的引擎，我们可以创建 `trans_hub/engines/awesome.py`。

### **4. 第二步：定义配置模型**

每个引擎都需要一个配置模型，用于从 `.env` 文件或环境变量中加载其特定的设置（如 API Key）。

打开你刚创建的 `awesome.py` 文件，添加如下代码：

```python
# trans_hub/engines/awesome.py

from pydantic import Field
from pydantic_settings import BaseSettings
# 导入 Trans-Hub 的基类
from trans_hub.engines.base import BaseEngineConfig

class AwesomeEngineConfig(BaseSettings):
    """
    AwesomeTranslate 引擎的配置模型。
    """
    # 保持与我们项目中其他配置模型的风格一致
    # 使用 validation_alias 来映射到环境变量
    api_key: str = Field(validation_alias='TH_AWESOME_API_KEY')
    # 假设它有一个可选的区域终结点
    region: str = Field(default='us-east-1', validation_alias='TH_AWESOME_REGION')

    # 继承 BaseEngineConfig 中的通用配置，如果需要的话
    #（或者直接在这里定义 rpm, rps 等）
```

**同时，别忘了在 `.env.example` 文件中为你的新引擎添加配置示例！**

```ini
# .env.example

# ==================================
# AwesomeTranslate 引擎配置
# ==================================
TH_AWESOME_API_KEY="your-awesome-api-key"
TH_AWESOME_REGION="us-east-1"
```

### **5. 第三步：实现引擎主类**

这是最核心的一步。你需要创建一个继承自 `BaseTranslationEngine` 的类。

```python
# trans_hub/engines/awesome.py

from typing import List, Optional
# 导入你的配置模型
from .awesome import AwesomeEngineConfig
# 导入 Trans-Hub 的基类和返回类型
from trans_hub.engines.base import BaseTranslationEngine, BaseContextModel
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess
# 假设有一个 awesome-translate 的 SDK
import awesome_sdk

class AwesomeEngine(BaseTranslationEngine):
    """一个对接 AwesomeTranslate 服务的翻译引擎。"""
    
    # 将你的配置模型与引擎类绑定
    CONFIG_MODEL = AwesomeEngineConfig
    # 定义一个版本号
    VERSION = "1.0.0"

    def __init__(self, config: AwesomeEngineConfig):
        super().__init__(config)
        # 在构造函数中，初始化与外部 API 通信所需的客户端
        try:
            self.client = awesome_sdk.Client(
                api_key=self.config.api_key,
                region=self.config.region
            )
        except Exception as e:
            # 如果初始化失败，应该抛出异常，让 Coordinator 知道此引擎不可用
            raise ConnectionError(f"初始化 AwesomeEngine 失败: {e}")

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
                # 调用 SDK/API 进行翻译
                api_response = self.client.translate(
                    text=text,
                    target=target_lang,
                    source=source_lang
                )
                
                # 将成功的响应包装成 EngineSuccess
                results.append(EngineSuccess(
                    translated_text=api_response.translated_text
                ))
                
            except awesome_sdk.RateLimitError as e:
                # 这是一个可重试的错误
                results.append(EngineError(error_message=str(e), is_retryable=True))
                
            except awesome_sdk.AuthError as e:
                # 这是一个不可重试的错误（API Key 错误）
                results.append(EngineError(error_message=str(e), is_retryable=False))
                
            except Exception as e:
                # 其他未知错误，通常假设为可重试
                results.append(EngineError(error_message=str(e), is_retryable=True))
                
        return results

    async def atranslate_batch(
        self, texts: List[str], target_lang: str,
        # ...
    ) -> List[EngineBatchItemResult]:
        # 如果你的 SDK 支持异步，请在这里实现异步逻辑
        # 否则，可以暂时调用同步版本或返回 NotImplementedError
        raise NotImplementedError("AwesomeEngine 的异步版本尚未实现。")
```

### **6. 第四步：注册你的引擎**

为了让 `Trans-Hub` 的动态发现机制能够找到你的新引擎，你需要做最后一步简单的修改。

打开 `trans_hub/config.py` 文件，在 `EngineConfigs` 模型中添加你的引擎配置。

```python
# trans_hub/config.py

# 1. 导入你的新配置模型
from trans_hub.engines.awesome import AwesomeEngineConfig
# ...

class EngineConfigs(BaseModel):
    debug: Optional[DebugEngineConfig] = Field(default_factory=DebugEngineConfig)
    openai: Optional[OpenAIEngineConfig] = None
    
    # 2. 在这里添加你的新引擎配置字段
    # 字段名应该是小写的引擎名，与注册表中的 key 一致
    awesome: Optional[AwesomeEngineConfig] = None
```

**完成了！** 就这么简单。`engine_registry` 现在会自动发现并注册你的 `AwesomeEngine`。

### **7. 第五步：编写测试**

为了确保你的引擎能够稳定工作，并能被我们的测试套件覆盖，请更新 `run_coordinator_test.py`。

1.  在文件顶部导入你的新引擎：`from trans_hub.engines.awesome import AwesomeEngine, AwesomeEngineConfig`。
2.  仿照 `test_openai_engine_flow`，创建一个新的测试函数 `test_awesome_engine_flow`。
3.  在这个新函数中，将 `active_engine` 设置为 `"awesome"`，并提供相应的配置。
4.  在 `main` 函数中调用你的新测试函数。

### **8. 提交你的贡献**

当你完成了以上所有步骤，并确保所有测试都能通过时，你就可以提交一个 Pull Request 到我们的主仓库了！请在 PR 中简要说明你的新引擎的功能和用法。

感谢你为 `Trans-Hub` 生态系统做出贡献！

### **9. 高级主题：处理上下文 (Context)**

如果你的引擎支持更高级的功能（比如术语表、正式/非正式语气等），你可以通过 `Context` 机制来实现。

1.  **定义 Context 模型**:
    ```python
    # awesome.py
    from trans_hub.engines.base import BaseContextModel
    
    class AwesomeContext(BaseContextModel):
        formality: str = "default" # e.g., "default", "formal", "informal"
    ```
2.  **绑定到引擎**:
    ```python
    # awesome.py
    class AwesomeEngine(BaseTranslationEngine):
        CONFIG_MODEL = AwesomeEngineConfig
        CONTEXT_MODEL = AwesomeContext # 绑定你的 Context 模型
        # ...
    ```
3.  **在 `translate_batch` 中使用**:
    ```python
    # awesome.py
    def translate_batch(self, ..., context: Optional[AwesomeContext] = None):
        if context:
            # 使用 context 中的值来调用 API
            api_response = self.client.translate(..., formality=context.formality)
        # ...
    ```

`Coordinator` 在接收到带 `context` 的 `request` 时，会自动使用你定义的 `CONTEXT_MODEL` 来验证和结构化 `context` 字典，然后将其传递给你的引擎。
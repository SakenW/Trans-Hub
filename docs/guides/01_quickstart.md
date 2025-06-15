# **指南 1：快速入门**

欢迎使用 `Trans-Hub`！本指南将向您展示如何在短短几分钟内，利用 `Trans-Hub` 的零配置特性，完成您的第一个翻译任务。您不需要任何 API 密钥或复杂的设置。

## **目标**

使用 `Trans-Hub` 的内置免费翻译引擎，将 "Hello, world!" 翻译成中文，并观察其智能缓存机制。

## **步骤 1：安装 `Trans-Hub`**

首先，请确保您的 Python 环境（建议使用 3.9 或更高版本）已准备好。然后，通过 pip 安装 `Trans-Hub` 核心库。它已经包含了运行免费翻译引擎所需的一切。

```bash
pip install trans-hub
```

## **步骤 2：编写您的第一个翻译脚本**

在您的项目目录中，创建一个新的 Python 文件，例如 `quick_start.py`。将以下代码复制并粘贴到文件中。

```python
# quick_start.py
import os
import structlog
from dotenv import load_dotenv

# 导入 Trans-Hub 的核心组件
from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler

# 获取一个 logger，用于结构化日志输出
log = structlog.get_logger()

def initialize_trans_hub():
    """
    一个标准的初始化函数，负责设置日志、数据库和 Coordinator。
    返回一个配置好的 Coordinator 实例。
    """
    # 初始化日志系统
    setup_logging(log_level="INFO")

    # 定义数据库文件名
    DB_FILE = "my_first_translations.db"

    # 在生产环境中，数据库迁移通常只在部署时执行一次。
    # 这里我们简化处理，如果数据库文件不存在，则创建并迁移。
    if not os.path.exists(DB_FILE):
        log.info("数据库不存在，正在创建并迁移...", db_path=DB_FILE)
        apply_migrations(DB_FILE)

    # 初始化持久化处理器，它负责所有数据库交互
    handler = DefaultPersistenceHandler(db_path=DB_FILE)

    # 创建一个最简单的配置对象。
    # 它将自动使用默认的、免费的 'translators' 引擎。
    config = TransHubConfig()

    # 使用配置和持久化处理器来创建主协调器
    coordinator = Coordinator(config=config, persistence_handler=handler)
    return coordinator

def main():
    """程序的主入口点。"""
    # 在程序最开始主动加载 .env 文件（如果存在），这是一个健壮的实践
    load_dotenv()

    # 初始化 Trans-Hub
    coordinator = initialize_trans_hub()
    try:
        # 定义我们要翻译的文本和目标语言
        text_to_translate = "Hello, world!"
        target_language_code = "zh-CN"

        # 登记一个翻译任务。这是一个轻量级操作。
        log.info("正在登记翻译任务", text=text_to_translate, lang=target_language_code)
        coordinator.request(
            target_langs=[target_language_code],
            text_content=text_to_translate,
            business_id="app.greeting.hello_world" # 关联一个业务ID，便于追踪
        )

        # 执行翻译。这是一个重量级操作，会真实调用 API。
        log.info(f"正在处理 '{target_language_code}' 的待翻译任务...")
        results = list(coordinator.process_pending_translations(
            target_lang=target_language_code
        ))

        # 处理并打印翻译结果
        if results:
            first_result = results[0]
            log.info(
                "翻译完成！",
                original=first_result.original_content,
                translation=first_result.translated_content,
                status=first_result.status.name,
                engine=first_result.engine,
                business_id=first_result.business_id # 显示关联的业务ID
            )
        else:
            log.warning("没有需要处理的新任务（可能已翻译过，这是缓存的体现）。")

    except Exception as e:
        log.critical("程序运行中发生未知严重错误！", exc_info=True)
    finally:
        # 确保在程序结束时关闭 Coordinator 和数据库连接
        if 'coordinator' in locals() and coordinator:
            coordinator.close()

if __name__ == "__main__":
    main()
```

## **步骤 3：运行脚本并观察结果**

现在，打开您的终端，并运行刚刚创建的脚本。

#### **第一次运行**

```bash
python quick_start.py
```

您将看到类似以下的输出。`Trans-Hub` 会创建数据库，登记任务，然后调用免费翻译引擎进行翻译。

```
INFO     数据库不存在，正在创建并迁移...            db_path=my_first_translations.db
INFO     正在登记翻译任务...                        text=Hello, world! lang=zh-CN
INFO     正在处理 'zh-CN' 的待翻译任务...
INFO     翻译完成！                                 original=Hello, world! translation=你好世界！ status=TRANSLATED engine=translators business_id=app.greeting.hello_world
```

#### **第二次运行**

**不要删除** `my_first_translations.db` 文件，再次运行同一个脚本：

```bash
python quick_start.py
```

这一次，您将看到不同的输出，这展示了 `Trans-Hub` 的智能缓存机制：

```
INFO     正在登记翻译任务...                        text=Hello, world! lang=zh-CN
INFO     正在处理 'zh-CN' 的待翻译任务...
WARNING  没有需要处理的新任务（可能已翻译过，这是缓存的体现）。
```

`Coordinator.process_pending_translations()` 发现这个翻译请求已经成功完成并缓存在数据库中，因此它跳过了 API 调用，为您节省了时间和成本。

**恭喜您！** 您已经成功地体验了 `Trans-Hub` 的核心功能。现在，您可以继续探索更多高级用法。
# 指南 1：快速入门

**目标**: 本指南将带您在 5 分钟内，完成从安装 `Trans-Hub` 到运行您的第一个异步翻译任务的全过程，并亲身体验其强大的智能缓存功能。

**前提**: 您已安装 Python 3.9+。

---

### 步骤 1：安装 Trans-Hub

首先，安装 `Trans-Hub` 的核心库。它已经包含了运行默认免费翻译引擎所需的一切，无需任何额外的依赖。

```bash
pip install trans-hub
```

### 步骤 2：创建您的翻译脚本

在您的项目目录中，创建一个名为 `quick_start.py` 的文件，并将以下代码完整地复制进去。

这段代码展示了初始化 `Trans-Hub` 并执行一个基本翻译任务的标准模式。

```python
# quick_start.py
import asyncio
import os
import structlog

from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler

log = structlog.get_logger()

async def initialize_trans_hub():
    """一个标准的异步初始化函数，返回一个配置好的 Coordinator 实例。"""
    DB_FILE = "my_translations.db"

    # 检查数据库文件是否存在，如果不存在，则创建并应用迁移。
    if not os.path.exists(DB_FILE):
        log.info("数据库不存在，正在创建并迁移...", db_path=DB_FILE)
        apply_migrations(DB_FILE)

    # 初始化默认的持久化处理器
    handler = DefaultPersistenceHandler(db_path=DB_FILE)

    # 创建一个最简单的配置对象。
    # 它将自动使用默认的、免费的 'translators' 引擎。
    config = TransHubConfig(database_url=f"sqlite:///{DB_FILE}")

    # 创建 Coordinator 实例
    coordinator = Coordinator(config=config, persistence_handler=handler)

    # Coordinator 必须被异步初始化以建立数据库连接
    await coordinator.initialize()
    return coordinator

async def main():
    """程序的主异步入口。"""
    setup_logging(log_level="INFO")
    coordinator = await initialize_trans_hub()

    try:
        text_to_translate = "Hello, world!"
        target_lang = "zh-CN"

        # 1. 登记任务：告诉 Trans-Hub 我们有一个翻译需求。
        log.info("正在登记翻译任务", text=text_to_translate, lang=target_lang)
        await coordinator.request(
            target_langs=[target_lang],
            text_content=text_to_translate,
            business_id="app.greeting.hello_world"
        )

        # 2. 执行任务：处理所有待办的翻译。
        log.info(f"正在处理 '{target_lang}' 的待翻译任务...")
        results = [res async for res in coordinator.process_pending_translations(target_lang=target_lang)]

        if results:
            log.info("翻译完成！", result=results[0])
        else:
            log.warning("没有需要处理的新任务（这是缓存机制在生效）。")

    finally:
        # 3. 清理资源：优雅地关闭数据库连接。
        if 'coordinator' in locals() and coordinator:
            await coordinator.close()

if __name__ == "__main__":
    # 这是运行异步 main 函数的标准方式
    asyncio.run(main())
```

### 步骤 3：运行并观察结果

现在，在您的终端中运行这个脚本。

```bash
python quick_start.py
```

#### 第一次运行（进行真实翻译）

您将看到类似以下的输出。`Trans-Hub` 创建了数据库，登记了任务，调用了翻译引擎，并打印了翻译结果。

```
... [info     ] 数据库不存在，正在创建并迁移...
... [info     ] 正在登记翻译任务...
... [info     ] 正在处理 'zh-CN' 的待翻译任务...
... [info     ] 翻译完成！ result=TranslationResult(original_content='Hello, world!', translated_content='你好，世界！', ...)
```

#### 第二次运行（体验智能缓存）

现在，**不要删除**生成的 `my_translations.db` 文件，**再次运行**完全相同的命令：

```bash
python quick_start.py
```

这一次，您将看到不同的输出。`Trans-Hub` 发现这个翻译任务已经存在于数据库中，因此 `process_pending_translations` 没有返回任何新的结果。

```
... [info     ] 正在登记翻译任务...
... [info     ] 正在处理 'zh-CN' 的待翻译任务...
... [warning  ] 没有需要处理的新任务（这是缓存机制在生效）。
```

---

### 恭喜！

您已经成功地运行了您的第一个 `Trans-Hub` 翻译任务，并验证了其核心的持久化缓存功能。

**下一步去哪里？**

- 准备好使用更强大的引擎了吗？请查阅我们的 **[高级用法指南](./02_advanced_usage.md)**。
- 想深入了解 `Trans-Hub` 的内部工作原理？请访问 **[架构文档](../architecture/01_overview.md)**。

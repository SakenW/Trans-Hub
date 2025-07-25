# 指南 1：快速入门

**目标**: 本指南将带您在 5 分钟内，完成从安装 `Trans-Hub` 到运行您的第一个异步翻译任务的全过程，并亲身体验其强大的智能缓存功能。

**前提**: 您已安装 Python 3.9+。

---

### 步骤 1：安装 Trans-Hub

首先，安装 `Trans-Hub` 的核心库。它已经包含了运行默认免费翻译引擎所需的一切，无需任何额外的依赖。

```bash
pip install "trans-hub[translators]"
```

### 步骤 2：创建您的翻译脚本

在您的项目目录中，创建一个名为 `quick_start.py` 的文件，并将以下代码完整地复制进去。

这段代码展示了初始化 `Trans-Hub` 并执行一个基本翻译任务的标准模式。

```python
# quick_start.py
import asyncio
from pathlib import Path

# 在您自己的项目中，您会直接 `import trans_hub`
# 这里我们为了让示例脚本能独立运行，需要手动设置路径
try:
    import trans_hub
except ImportError:
    import sys
    # 将项目根目录添加到 Python 路径中
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(PROJECT_ROOT))

from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler

async def get_or_create_coordinator(db_name: str = "my_translations.db"):
    """
    一个健壮的异步工厂函数，用于获取一个初始化完成的 Coordinator 实例。
    """
    # 使用 pathlib 确保数据库路径的健壮性
    db_path = Path(__file__).parent / db_name
    log = structlog.get_logger("initializer")

    # 首次运行时，创建数据库并应用迁移
    if not db_path.exists():
        log.info("数据库不存在，正在创建并迁移...", db_path=str(db_path))
        apply_migrations(str(db_path))

    # 使用绝对路径初始化配置，避免任何歧义
    config = TransHubConfig(database_url=f"sqlite:///{db_path.resolve()}")
    handler = DefaultPersistenceHandler(db_path=config.db_path)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    # 异步初始化 Coordinator 以建立数据库连接
    await coordinator.initialize()
    return coordinator

async def main():
    """程序的主异步入口。"""
    setup_logging(log_level="INFO")
    log = structlog.get_logger("main")
    coordinator = None

    try:
        coordinator = await get_or_create_coordinator()

        text_to_translate = "Hello, world!"
        target_lang = "zh-CN"
        text_id = "app.greeting.hello_world"

        # --- 第一次运行 ---
        log.info("▶️ 第一次尝试翻译...")

        # 1. 登记任务
        log.info("登记翻译任务", text=text_to_translate, business_id=text_id)
        await coordinator.request(
            target_langs=[target_lang],
            text_content=text_to_translate,
            business_id=text_id
        )

        # 2. 执行待处理的任务
        log.info(f"处理 '{target_lang}' 的待翻译任务...")
        processed_results = [
            res async for res in coordinator.process_pending_translations(target_lang=target_lang)
        ]

        if processed_results:
            log.info("翻译完成！", result=processed_results[0])
        else:
            log.warning("没有需要处理的新任务。")

        # --- 第二次运行 (模拟) ---
        log.info("\n▶️ 第二次尝试翻译 (模拟缓存命中)...")

        # 1. 再次登记同一个任务
        log.info("再次登记同一个翻译任务", text=text_to_translate, business_id=text_id)
        await coordinator.request(
            target_langs=[target_lang],
            text_content=text_to_translate,
            business_id=text_id
        )

        # 2. 再次执行
        log.info(f"再次处理 '{target_lang}' 的待翻译任务...")
        processed_again = [
            res async for res in coordinator.process_pending_translations(target_lang=target_lang)
        ]

        if not processed_again:
            log.info("✅ 成功！没有需要处理的新任务，表明持久化缓存生效。")
            # 我们可以直接从数据库获取已有的翻译
            existing_translation = await coordinator.get_translation(
                text_content=text_to_translate, target_lang=target_lang
            )
            if existing_translation:
                log.info("直接从数据库获取到已有的翻译", result=existing_translation)

    except Exception as e:
        log.error("程序发生意外错误", error=str(e), exc_info=True)
    finally:
        if coordinator:
            await coordinator.close()
            log.info("数据库连接已关闭。")

if __name__ == "__main__":
    import structlog
    asyncio.run(main())
```

### 步骤 3：运行并观察结果

现在，在您的终端中运行这个脚本。

```bash
python quick_start.py
```

您将看到一个完整的流程，脚本在一次运行中就演示了首次翻译和缓存命中两种情况，无需您手动运行两次。

---

### 恭喜！

您已经成功地运行了您的第一个 `Trans-Hub` 翻译任务，并验证了其核心的持久化缓存功能。

**下一步去哪里？**

- 准备好使用更强大的引擎了吗？请查阅我们的 **[高级用法指南](./02_advanced_usage.md)**。
- 想深入了解 `Trans-Hub` 的内部工作原理？请访问 **[架构文档](../architecture/01_overview.md)**。

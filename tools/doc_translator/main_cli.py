# tools/doc_translator/main_cli.py
"""Trans-Hub 文档翻译同步工具的命令行入口。"""

import argparse
import asyncio
import sys
from pathlib import Path

import structlog

# -- 路径设置 --
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trans_hub import (  # noqa: E402
    Coordinator,
    DefaultPersistenceHandler,
    TransHubConfig,
)
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402

from .synchronizer import DocSynchronizer  # noqa: E402

# --- 数据库配置 ---
# 这个数据库将作为本地的、持久化的翻译缓存
DB_FILE_PATH = PROJECT_ROOT / "tools" / "doc_translator" / "docs_translations.db"


async def main():
    parser = argparse.ArgumentParser(
        description="""
        Trans-Hub 文档翻译同步工具。
        该工具会扫描 `docs/` 目录下的中文源文件 (*.zh.md)，
        将其内容通过 Trans-Hub 翻译，并生成/更新其他语言的版本。
        """
    )
    # [核心简化] 现在只有一个 'sync' 命令，我们可以让它成为默认行为
    # parser.add_argument("command", nargs="?", default="sync", help="要执行的命令 (默认为 'sync')")
    # 为了更简单，我们甚至可以移除子命令，让脚本直接执行同步

    parser.parse_args()

    setup_logging(log_level="INFO")
    log = structlog.get_logger()

    log.info("▶️ 启动文档翻译同步...")

    # 首次运行时，创建并迁移数据库
    if not DB_FILE_PATH.exists():
        log.info("数据库不存在，正在创建...", path=str(DB_FILE_PATH))
        apply_migrations(str(DB_FILE_PATH))

    # 初始化 Trans-Hub
    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE_PATH.resolve()}",
        active_engine="openai",
        source_lang="zh",
    )
    handler = DefaultPersistenceHandler(config.db_path)
    coordinator = Coordinator(config, handler)

    try:
        await coordinator.initialize()
        synchronizer = DocSynchronizer(coordinator)
        await synchronizer.run_sync()
        log.info("✅ 文档翻译同步完成！")
    except Exception:
        log.error("文档同步过程中发生意外错误。", exc_info=True)
    finally:
        if coordinator and coordinator.initialized:
            await coordinator.close()


if __name__ == "__main__":
    asyncio.run(main())

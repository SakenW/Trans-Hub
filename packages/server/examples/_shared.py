# examples/_shared.py
# [v1.1 Final] 修正 ModuleNotFoundError，使用 Alembic API 运行迁移。
"""
包含所有示例共享的辅助函数和上下文管理器，以减少重复代码。
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import structlog

# --- 路径设置 ---
current_dir = Path(__file__).parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
# ---

# [核心修正] 导入 Alembic
from alembic import command
from alembic.config import Config as AlembicConfig
from trans_hub import Coordinator, TransHubConfig
from trans_hub.core import TranslationResult
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import create_persistence_handler

# --- 日志配置 ---
setup_logging(log_level="INFO")
log = structlog.get_logger("trans_hub_example")


def apply_migrations(db_url: str) -> None:
    """使用 Alembic API 以编程方式应用数据库迁移。"""
    if "sqlite" not in db_url:
        return # 目前示例只针对 SQLite
        
    alembic_cfg_path = project_root / "alembic.ini"
    if not alembic_cfg_path.is_file():
        log.error("Alembic config file not found!", path=alembic_cfg_path)
        return
        
    alembic_cfg = AlembicConfig(str(alembic_cfg_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url.replace("+aiosqlite", ""))
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def example_runner(
    db_file_name: str, **config_overrides: Any
) -> AsyncGenerator[Coordinator, None]:
    """
    一个异步上下文管理器，负责准备和清理示例的运行环境。
    """
    db_file = current_dir / db_file_name
    if db_file.exists():
        db_file.unlink()

    database_url = f"sqlite+aiosqlite:///{db_file.resolve()}"
    apply_migrations(database_url)

    base_config = {"database_url": database_url, "source_lang": "en"}
    final_config = {**base_config, **config_overrides}

    config = TransHubConfig(**final_config)
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        await coordinator.initialize()
        log.info(f"✅ 示例环境已就绪", db_path=str(db_file))
        yield coordinator
    finally:
        await coordinator.close()
        log.info("🚪 协调器已关闭")
        if db_file.exists():
            db_file.unlink()


async def process_translations(coordinator: Coordinator, langs: list[str]) -> None:
    """模拟 Worker 处理所有待办任务。"""
    tasks = [asyncio.create_task(consume_all(coordinator, lang)) for lang in langs]
    await asyncio.gather(*tasks)


async def consume_all(coordinator: Coordinator, lang: str) -> None:
    """消费指定语言的所有待办任务。"""
    results: list[TranslationResult] = [
        res async for res in coordinator.handler.stream_draft_translations(batch_size=10)
    ]
    log.info(f"Worker 为语言 '{lang}' 处理了 {len(results)} 个任务批次。")
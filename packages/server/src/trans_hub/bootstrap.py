# packages/server/src/trans_hub/bootstrap.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Literal
import structlog

from trans_hub.application import Coordinator
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.db import (
    create_async_db_engine,
    create_async_sessionmaker,
)
from trans_hub.infrastructure.uow import SqlAlchemyUnitOfWork, UowFactory

SERVER_ROOT_DIR = Path(__file__).resolve().parents[2]
MONOREPO_ROOT = SERVER_ROOT_DIR.parent.parent


# --- .env 加载逻辑 (保持不变) ---
def _load_dotenv_files(env_mode: Literal["prod", "dev", "test"]) -> list[Path]:
    files_to_load: list[Path] = []
    base_env = SERVER_ROOT_DIR / ".env"
    if base_env.is_file():
        files_to_load.append(base_env)
    dev_env = SERVER_ROOT_DIR / ".env.dev"
    if env_mode in ("dev", "test") and dev_env.is_file():
        files_to_load.append(dev_env)
    test_env = SERVER_ROOT_DIR / ".env.test"
    if env_mode == "test" and test_env.is_file():
        files_to_load.append(test_env)
    logger = structlog.get_logger("trans_hub.bootstrap.dotenv")
    logger.debug(
        "Dotenv files determined for loading",
        files=[str(p.relative_to(MONOREPO_ROOT)) for p in files_to_load],
    )
    for file_path in files_to_load:
        try:
            with file_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    if (value.startswith("'") and value.endswith("'")) or (
                        value.startswith('"') and value.endswith('"')
                    ):
                        value = value[1:-1]
                    os.environ[key] = value
        except Exception as e:
            logger.warning(
                "Failed to parse .env file", path=str(file_path), error=str(e)
            )
    return files_to_load


def _ensure_no_legacy_prefix() -> None:
    legacy = [k for k in os.environ.keys() if k.startswith("TH_")]
    if legacy:
        raise RuntimeError(f"检测到遗留环境变量前缀 TH_：{legacy}...")


# --- 核心工厂函数 ---


def create_app_config(env_mode: Literal["prod", "dev", "test"]) -> TransHubConfig:
    """加载并返回应用配置对象。"""
    _ensure_no_legacy_prefix()
    files_loaded = _load_dotenv_files(env_mode)
    config = TransHubConfig()
    logger = structlog.get_logger("trans_hub.bootstrap.final")
    logger.debug(
        "Config instance created",
        env_mode=env_mode,
        files_manually_loaded=[str(p.relative_to(MONOREPO_ROOT)) for p in files_loaded],
        final_db_url=config.database.url,
        final_maint_url=config.maintenance_database_url,
    )
    return config


def create_uow_factory(config: TransHubConfig) -> tuple[UowFactory, Any]:
    """创建 UoW 工厂和数据库引擎。"""
    db_engine = create_async_db_engine(config)
    sessionmaker = create_async_sessionmaker(db_engine)

    def uow_factory():
        return SqlAlchemyUnitOfWork(sessionmaker)

    return uow_factory, db_engine


async def create_coordinator(config: TransHubConfig) -> tuple[Coordinator, Any]:
    """
    创建并组装一个完全配置的 Coordinator 实例及其依赖。
    返回 Coordinator 实例和数据库引擎（用于生命周期管理）。
    """
    uow_factory, db_engine = create_uow_factory(config)

    stream_producer = None
    cache_handler = None

    if config.redis.url:
        from trans_hub.infrastructure.redis._client import get_redis_client
        from trans_hub.infrastructure.redis.cache import RedisCacheHandler
        from trans_hub.infrastructure.redis.streams import RedisStreamProducer

        redis_client = await get_redis_client(config)
        stream_producer = RedisStreamProducer(redis_client)
        cache_handler = RedisCacheHandler(redis_client, config.redis.key_prefix)
        structlog.get_logger("trans_hub.bootstrap").info("Redis 基础设施已初始化。")

    coordinator = Coordinator(
        config=config,
        uow_factory=uow_factory,
        stream_producer=stream_producer,
        cache=cache_handler,
    )
    await coordinator.initialize()
    return coordinator, db_engine

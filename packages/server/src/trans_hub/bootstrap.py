# packages/server/src/trans_hub/bootstrap.py
"""
应用引导程序。

本模块是应用的初始化和依赖注入 (DI) 中心，负责加载配置、
创建核心服务实例（如 UoW 工厂、应用服务）并组装它们。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Any

import structlog

from trans_hub.application import Coordinator
from trans_hub.application.resolvers import TranslationResolver
from trans_hub.application.services import (
    CommentingService,
    RequestTranslationService,
    RevisionLifecycleService,
    TranslationQueryService,
)
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.db import (
    create_async_db_engine,
    create_async_sessionmaker,
)
from trans_hub.infrastructure.uow import SqlAlchemyUnitOfWork, UowFactory
from trans_hub.management.config_utils import mask_db_url

SERVER_ROOT_DIR = Path(__file__).resolve().parents[2]
MONOREPO_ROOT = SERVER_ROOT_DIR.parent.parent
logger = structlog.get_logger("trans_hub.bootstrap")


# --- .env 加载逻辑 ---
def _load_dotenv_files(env_mode: Literal["prod", "dev", "test"]) -> list[Path]:
    """根据环境模式，确定并加载相应的 .env 文件。"""
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
    """确保没有使用旧的 TH_ 环境变量前缀。"""
    legacy = [k for k in os.environ.keys() if k.startswith("TH_")]
    if legacy:
        raise RuntimeError(f"检测到遗留环境变量前缀 TH_：{legacy}...")


# --- 核心工厂函数 ---


def create_app_config(env_mode: Literal["prod", "dev", "test"]) -> TransHubConfig:
    """加载、验证并返回应用配置对象。"""
    _ensure_no_legacy_prefix()
    _load_dotenv_files(env_mode)
    config = TransHubConfig()
    logger.debug(
        "Config instance created",
        env_mode=env_mode,
        # [修改] 使用新的工具函数进行安全打印
        final_db_url=mask_db_url(config.database.url),
        final_maint_url=mask_db_url(config.maintenance_database_url)
        if config.maintenance_database_url
        else None,
    )
    return config


def create_uow_factory(config: TransHubConfig) -> tuple[UowFactory, Any]:
    """创建 UoW 工厂和底层的数据库引擎。"""
    db_engine = create_async_db_engine(config)
    sessionmaker = create_async_sessionmaker(db_engine)

    def uow_factory():
        return SqlAlchemyUnitOfWork(sessionmaker)

    return uow_factory, db_engine


async def create_coordinator(config: TransHubConfig) -> tuple[Coordinator, Any]:
    """
    创建并组装一个完全配置的 Coordinator 实例及其所有依赖的服务。
    返回 Coordinator 实例和数据库引擎（用于生命周期管理）。
    """
    uow_factory, db_engine = create_uow_factory(config)

    _stream_producer, cache_handler = None, None
    if config.redis.url:
        from trans_hub.infrastructure.redis._client import get_redis_client
        from trans_hub.infrastructure.redis.cache import RedisCacheHandler
        from trans_hub.infrastructure.redis.streams import RedisStreamProducer

        redis_client = await get_redis_client(config)
        RedisStreamProducer(redis_client)
        cache_handler = RedisCacheHandler(redis_client, config.redis.key_prefix)
        logger.info("Redis 基础设施已初始化 (Stream, Cache)。")

    # 1. 实例化所有依赖和服务
    resolver = TranslationResolver(uow_factory)

    request_service = RequestTranslationService(uow_factory, config)
    lifecycle_service = RevisionLifecycleService(uow_factory, config)
    commenting_service = CommentingService(uow_factory, config)
    query_service = TranslationQueryService(
        uow_factory, config, cache_handler, resolver
    )

    # 2. 将所有服务注入到 Coordinator 门面
    coordinator = Coordinator(
        request_service=request_service,
        lifecycle_service=lifecycle_service,
        commenting_service=commenting_service,
        query_service=query_service,
    )

    # 3. 执行简单的初始化（如果需要）
    await coordinator.initialize()

    return coordinator, db_engine

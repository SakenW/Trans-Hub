# packages/server/src/trans_hub/infrastructure/db/engine.py
"""
异步引擎工厂（最优化实现，遵守技术宪章）

- Postgres：映射连接池参数（QueuePool）
- SQLite：NullPool，忽略不适用的池参数

此模块还负责根据数据库方言动态创建和关联 `MetaData` 对象，
确保在 SQLite 中不使用 schema，而在 PostgreSQL 中使用配置的 schema。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from ...config import TransHubConfig
from .base import metadata


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite+aiosqlite") or url.startswith("sqlite://")


def create_async_db_engine(cfg: TransHubConfig) -> AsyncEngine:
    """创建符合最优化策略的 AsyncEngine，并动态关联 MetaData。"""
    url = cfg.database.url
    is_sqlite = _is_sqlite(url)

    # 1. 根据方言动态设置 MetaData 的 schema
    #    - SQLite 不支持 schema，所以为 None
    #    - 其他数据库（如 PostgreSQL）使用配置中定义的 schema
    #    所有 ORM 模型通过 base.py 中的 Base 类自动与这个 metadata 实例关联。
    metadata.schema = None if is_sqlite else cfg.database.default_schema

    # 2. 准备引擎创建参数
    kwargs: dict[str, Any] = {
        "echo": cfg.db_echo or getattr(cfg.database, "echo", False),
        "pool_pre_ping": cfg.db_pool_pre_ping,
        "future": True,
    }

    if is_sqlite:
        # SQLite 推荐使用 NullPool，避免多进程/多线程下的共享句柄问题
        kwargs["poolclass"] = NullPool
    else:
        # 仅在非 SQLite 时应用池参数
        if cfg.db_pool_size is not None:
            kwargs["pool_size"] = cfg.db_pool_size
        if cfg.db_max_overflow is not None:
            kwargs["max_overflow"] = cfg.db_max_overflow
        if cfg.db_pool_recycle is not None:
            kwargs["pool_recycle"] = cfg.db_pool_recycle
        kwargs["pool_timeout"] = cfg.db_pool_timeout

    # 5. 创建并返回引擎
    return create_async_engine(url, **kwargs)

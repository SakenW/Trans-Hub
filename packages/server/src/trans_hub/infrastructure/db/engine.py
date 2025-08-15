# packages/server/src/trans_hub/infrastructure/db/engine.py
"""
异步引擎工厂（最优化实现，遵守技术宪章）

- Postgres：映射连接池参数（QueuePool）
- SQLite：NullPool，忽略不适用的池参数
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from ...config import TransHubConfig


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite+aiosqlite") or url.startswith("sqlite://")


def create_async_db_engine(cfg: TransHubConfig) -> AsyncEngine:
    """创建符合最优化策略的 AsyncEngine。"""
    url = cfg.database.url
    kwargs: dict[str, Any] = {
        "echo": cfg.db_echo or getattr(cfg.database, "echo", False),
        "pool_pre_ping": cfg.db_pool_pre_ping,
        "future": True,
    }

    if _is_sqlite(url):
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

    return create_async_engine(url, **kwargs)

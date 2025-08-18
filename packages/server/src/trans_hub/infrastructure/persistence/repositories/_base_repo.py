# packages/server/src/trans_hub/infrastructure/persistence/repositories/_base_repo.py
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """所有 SQLAlchemy 仓库的基类。"""

    def __init__(self, session: "AsyncSession"):
        self._session = session

# packages/server/src/trans_hub/infrastructure/persistence/_statements.py
"""
数据库方言特定的 SQL 语句工厂。

本模块通过协议和具体实现，将 PostgreSQL 和 SQLite 的 INSERT ... ON CONFLICT
等方言差异与上层业务逻辑完全解耦。
"""
from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


class StatementFactory(Protocol):
    """
    定义了数据库方言特定语句生成器的接口协议。
    """

    def create_upsert_stmt(
        self,
        model: Any,
        values: dict[str, Any],
        index_elements: list[str],
        update_cols: list[str],
    ) -> Any:
        """
        创建一个原子化的 UPSERT (INSERT ... ON CONFLICT ... DO UPDATE) 语句。
        """
        ...

    def create_insert_on_conflict_nothing(
        self,
        model: Any,
        values: dict[str, Any],
        index_elements: list[str],
    ) -> Any:
        """
        创建一个原子化的 INSERT ... ON CONFLICT ... DO NOTHING 语句。
        """
        ...


class PostgresStatementFactory:
    """PostgreSQL 语句工厂实现。"""

    def create_upsert_stmt(
        self,
        model: Any,
        values: dict[str, Any],
        index_elements: list[str],
        update_cols: list[str],
    ) -> Any:
        stmt = pg_insert(model).values(**values)
        update_dict = {
            col.name: getattr(stmt.excluded, col.name)
            for col in model.__table__.columns
            if col.name in update_cols
        }
        if "updated_at" in [c.name for c in model.__table__.columns]:
            update_dict["updated_at"] = func.now()

        return stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_=update_dict,
        )

    def create_insert_on_conflict_nothing(
        self,
        model: Any,
        values: dict[str, Any],
        index_elements: list[str],
    ) -> Any:
        return pg_insert(model).values(**values).on_conflict_do_nothing(
            index_elements=index_elements
        )


class SQLiteStatementFactory:
    """SQLite 语句工厂实现。"""

    def create_upsert_stmt(
        self,
        model: Any,
        values: dict[str, Any],
        index_elements: list[str],
        update_cols: list[str],
    ) -> Any:
        stmt = sqlite_insert(model).values(**values)
        update_dict = {col: getattr(stmt.excluded, col) for col in update_cols}
        if "updated_at" in [c.name for c in model.__table__.columns]:
            update_dict["updated_at"] = func.now()

        return stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_=update_dict,
        )

    def create_insert_on_conflict_nothing(
        self,
        model: Any,
        values: dict[str, Any],
        index_elements: list[str],
    ) -> Any:
        return sqlite_insert(model).values(**values).on_conflict_do_nothing(
            index_elements=index_elements
        )
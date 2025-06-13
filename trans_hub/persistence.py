# trans_hub/persistence.py
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional

import structlog

from trans_hub.interfaces import PersistenceHandler
from trans_hub.types import (
    ContentItem,
    SourceUpdateResult,
    TranslationResult,
    TranslationStatus,
)

logger = structlog.get_logger(__name__)


class DefaultPersistenceHandler(PersistenceHandler):
    """使用标准库 `sqlite3` 实现的、与最终版文档对齐的同步持久化处理器。"""

    def __init__(self, db_path: str):
        """初始化处理器并建立数据库连接。"""
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()

    def _connect(self):
        """内部方法，用于建立和配置数据库连接。"""
        try:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute("PRAGMA journal_mode = WAL;")
        except sqlite3.Error:
            logger.error("连接数据库失败", exc_info=True)
            raise

    @property
    def connection(self) -> sqlite3.Connection:
        """提供一个安全的属性来访问连接对象，确保它不是 None。"""
        if self._conn is None:
            raise RuntimeError("数据库未连接。")
        return self._conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """一个提供原子事务的上下文管理器。"""
        cursor = self.connection.cursor()
        try:
            cursor.execute("BEGIN;")
            yield cursor
            self.connection.commit()
        except Exception:
            logger.error("事务执行失败，正在回滚", exc_info=True)
            self.connection.rollback()
            raise

    def touch_source(self, business_id: str) -> None:
        """更新指定 business_id 的 last_seen_at 时间戳到当前时间。"""
        with self.transaction() as cursor:
            sql = "UPDATE th_sources SET last_seen_at = ? WHERE business_id = ?"
            now = datetime.now(timezone.utc)
            cursor.execute(sql, (now.isoformat(), business_id))
            if cursor.rowcount > 0:
                logger.debug(
                    "Touched source record.",
                    business_id=business_id,
                    last_seen_at=now.isoformat(),
                )

    def update_or_create_source(
        self, text_content: str, business_id: str, context_hash: str
    ) -> SourceUpdateResult:
        """根据 `business_id` 更新或创建一个源记录。"""
        with self.transaction() as cursor:
            cursor.execute("SELECT id FROM th_content WHERE value = ?", (text_content,))
            content_row = cursor.fetchone()

            is_newly_created = False
            if content_row:
                content_id = content_row["id"]
            else:
                cursor.execute(
                    "INSERT INTO th_content (value) VALUES (?)", (text_content,)
                )
                content_id = cursor.lastrowid
                is_newly_created = True

            sql = """
                INSERT INTO th_sources (business_id, content_id, context_hash, last_seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(business_id) DO UPDATE SET
                    content_id = excluded.content_id,
                    context_hash = excluded.context_hash,
                    last_seen_at = excluded.last_seen_at;
            """
            now = datetime.now(timezone.utc)
            cursor.execute(
                sql, (business_id, content_id, context_hash, now.isoformat())
            )

            return SourceUpdateResult(
                content_id=content_id, is_newly_created=is_newly_created
            )

    def stream_translatable_items(
        self,
        lang_code: str,
        statuses: List[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> Generator[List[ContentItem], None, None]:
        """以流式方式获取待翻译的内容批次。"""
        status_values = tuple(s.value for s in statuses)
        limit_clause = f"LIMIT {limit}" if limit is not None else ""

        translation_ids = []
        with self.transaction() as cursor:
            find_ids_sql = f"""
                SELECT id FROM th_translations
                WHERE lang_code = ? AND status IN ({','.join('?' for _ in status_values)})
                ORDER BY last_updated_at ASC
                {limit_clause}
            """
            params = [lang_code] + list(status_values)
            cursor.execute(find_ids_sql, params)
            translation_ids = [row["id"] for row in cursor.fetchall()]

            if not translation_ids:
                return

            update_sql = f"""
                UPDATE th_translations SET status = ?, last_updated_at = ?
                WHERE id IN ({','.join('?' for _ in translation_ids)})
            """
            now = datetime.now(timezone.utc)
            update_params = [
                TranslationStatus.TRANSLATING.value,
                now.isoformat(),
            ] + translation_ids
            cursor.execute(update_sql, update_params)

        for i in range(0, len(translation_ids), batch_size):
            batch_ids = translation_ids[i : i + batch_size]
            get_details_sql = f"""
                SELECT tr.content_id, c.value, tr.context_hash
                FROM th_translations tr
                JOIN th_content c ON tr.content_id = c.id
                WHERE tr.id IN ({','.join('?' for _ in batch_ids)})
            """
            read_cursor = self.connection.cursor()
            read_cursor.execute(get_details_sql, batch_ids)

            yield [
                ContentItem(
                    content_id=row["content_id"],
                    value=row["value"],
                    context_hash=row["context_hash"],
                )
                for row in read_cursor.fetchall()
            ]

    def save_translations(self, results: List[TranslationResult]) -> None:
        """将一批翻译结果保存到数据库中。"""
        if not results:
            return

        update_params_list = []
        for res in results:
            content_id = self._get_content_id_from_value(res.original_content)
            if content_id is None:
                continue

            update_params_list.append(
                {
                    "status": res.status.value,
                    "translation_content": res.translated_content,
                    "engine": res.engine,
                    "last_updated_at": datetime.now(timezone.utc).isoformat(),
                    "content_id": content_id,
                    "lang_code": res.target_lang,
                    "context_hash": res.context_hash,
                }
            )

        if not update_params_list:
            return

        with self.transaction() as cursor:
            update_sql = """
                UPDATE th_translations SET
                    status = :status,
                    translation_content = :translation_content,
                    engine = :engine,
                    last_updated_at = :last_updated_at
                WHERE content_id = :content_id
                  AND lang_code = :lang_code
                  AND context_hash = :context_hash
                  AND status = 'TRANSLATING'
            """
            cursor.executemany(update_sql, update_params_list)
            logger.info(f"成功更新了 {cursor.rowcount} 条翻译记录。")

    def _get_content_id_from_value(self, value: str) -> Optional[int]:
        """辅助方法，根据内容值查找其在 `th_content` 表中的 ID。"""
        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM th_content WHERE value = ?", (value,))
        row = cursor.fetchone()
        return row["id"] if row else None

    def get_translation(
        self,
        text_content: str,
        target_lang: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        """根据文本内容、目标语言和上下文，从数据库中获取已翻译的结果。"""
        from trans_hub.utils import get_context_hash as _get_context_hash_util

        context_hash_for_query = _get_context_hash_util(context)

        cursor = self.connection.cursor()
        content_id = self._get_content_id_from_value(text_content)
        if not content_id:
            return None

        query_sql = """
            SELECT
                tr.translation_content, tr.status, tr.engine
            FROM th_translations tr
            WHERE tr.content_id = ? AND tr.lang_code = ? AND tr.context_hash = ? AND tr.status = ?
        """
        cursor.execute(
            query_sql,
            (
                content_id,
                target_lang,
                context_hash_for_query,
                TranslationStatus.TRANSLATED.value,
            ),
        )
        translation_row = cursor.fetchone()

        if translation_row:
            retrieved_business_id = self.get_business_id_for_content(
                content_id=content_id, context_hash=context_hash_for_query
            )
            return TranslationResult(
                original_content=text_content,
                translated_content=translation_row["translation_content"],
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                engine=translation_row["engine"],
                from_cache=True,
                business_id=retrieved_business_id,
                context_hash=context_hash_for_query,
            )
        return None

    def get_business_id_for_content(
        self, content_id: int, context_hash: str
    ) -> Optional[str]:
        """根据 `content_id` 和 `context_hash` 从 `th_sources` 表获取 `business_id`。"""
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT business_id FROM th_sources WHERE content_id = ? AND context_hash = ?",
            (content_id, context_hash),
        )
        row = cursor.fetchone()
        return row["business_id"] if row else None

    def garbage_collect(self, retention_days: int, dry_run: bool = False) -> dict:
        """执行垃圾回收，清理过时和孤立的数据。"""
        if retention_days < 0:
            raise ValueError("retention_days 必须是非负数。")

        cutoff_date = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).date()
        cutoff_date_str = cutoff_date.isoformat()

        stats = {"deleted_sources": 0, "deleted_content": 0}

        with self.transaction() as cursor:
            # --- 阶段 1: 清理过时的 th_sources 记录 ---
            select_expired_sources_sql = (
                "SELECT COUNT(*) FROM th_sources WHERE DATE(last_seen_at) < ?"
            )
            cursor.execute(select_expired_sources_sql, (cutoff_date_str,))
            expired_sources_count = cursor.fetchone()[0]
            stats["deleted_sources"] = expired_sources_count

            if not dry_run and expired_sources_count > 0:
                delete_expired_sources_sql = (
                    "DELETE FROM th_sources WHERE DATE(last_seen_at) < ?"
                )
                cursor.execute(delete_expired_sources_sql, (cutoff_date_str,))
                assert cursor.rowcount == expired_sources_count

            # --- 阶段 2: 清理孤立的 th_content 记录 ---
            select_orphan_content_sql = """
                SELECT COUNT(c.id)
                FROM th_content c
                WHERE
                    DATE(c.created_at) < ?
                    AND NOT EXISTS (SELECT 1 FROM th_sources s WHERE s.content_id = c.id)
                    AND NOT EXISTS (SELECT 1 FROM th_translations tr WHERE tr.content_id = c.id)
            """
            cursor.execute(select_orphan_content_sql, (cutoff_date_str,))
            orphan_content_count = cursor.fetchone()[0]
            stats["deleted_content"] = orphan_content_count

            if not dry_run and orphan_content_count > 0:
                delete_orphan_content_sql = """
                    DELETE FROM th_content
                    WHERE id IN (
                        SELECT c.id
                        FROM th_content c
                        WHERE
                            DATE(c.created_at) < ?
                            AND NOT EXISTS (SELECT 1 FROM th_sources s WHERE s.content_id = c.id)
                            AND NOT EXISTS (SELECT 1 FROM th_translations tr WHERE tr.content_id = c.id)
                    )
                """
                cursor.execute(delete_orphan_content_sql, (cutoff_date_str,))
                assert cursor.rowcount == orphan_content_count

        return stats

    def close(self) -> None:
        """关闭数据库连接，释放资源。"""
        if self._conn:
            self._conn.close()
            self._conn = None


if __name__ == "__main__":
    import os
    import sys

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from trans_hub.utils import get_context_hash

    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("pydantic").setLevel(logging.INFO)

    DB_FILE = "transhub_test.db"
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    from trans_hub.db.schema_manager import apply_migrations

    apply_migrations(DB_FILE)

    handler = DefaultPersistenceHandler(DB_FILE)
    try:
        # 1. 准备数据
        handler.update_or_create_source("hello", "bid1", get_context_hash(None))
        handler.touch_source("bid1")  # 模拟 Coordinator 处理

        # 手动创建过时数据
        with handler.transaction() as cursor:
            two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            cursor.execute(
                "INSERT INTO th_content (id, value) VALUES (100, 'old_content')"
            )
            cursor.execute(
                "INSERT INTO th_sources (business_id, content_id, context_hash, last_seen_at) VALUES (?, ?, ?, ?)",
                ("bid_old", 100, get_context_hash(None), two_days_ago),
            )

        # 2. 测试 GC
        stats = handler.garbage_collect(retention_days=1)
        assert stats["deleted_sources"] == 1

        with handler.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM th_sources")
            assert cursor.fetchone()[0] == 1

        print("✅ DefaultPersistenceHandler (v1.1) 自测试通过！")

    finally:
        handler.close()

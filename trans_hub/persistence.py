"""trans_hub/persistence.py (v1.0 Final - 第四次修正版)

本模块提供了持久化处理器的具体实现。
它实现了 `PersistenceHandler` 接口，并负责与数据库进行所有交互。
此版本已修复了 `sqlite3.Cursor` 不支持上下文管理协议的问题。
"""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator, List, Optional, Dict, Any

import structlog

# [变更] 导入已更新的 DTOs 和常量
from trans_hub.interfaces import PersistenceHandler
from trans_hub.types import (
    ContentItem,
    SourceUpdateResult,
    TranslationResult,
    TranslationStatus,
    GLOBAL_CONTEXT_SENTINEL # 导入全局上下文哨兵值
)

# 获取一个模块级别的日志记录器
logger = structlog.get_logger(__name__)


class DefaultPersistenceHandler(PersistenceHandler):
    """使用标准库 `sqlite3` 实现的、与最终版文档对齐的同步持久化处理器。
    这个类是数据库操作的唯一入口，封装了所有 SQL 查询，保证了上层代码的整洁。
    """

    def __init__(self, db_path: str):
        """初始化处理器并建立数据库连接。
        连接在对象生命周期内被复用，避免了频繁创建和销毁连接的开销。

        Args:
        ----
            db_path: SQLite 数据库文件的路径。

        """
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
        except sqlite3.Error as e:
            logger.error(f"连接数据库失败: {e}", exc_info=True)
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
        except Exception as e:
            logger.error(f"事务执行失败，正在回滚: {e}", exc_info=True)
            self.connection.rollback()
            raise

    def update_or_create_source(
        self, text_content: str, business_id: str, context_hash: str
    ) -> SourceUpdateResult:
        """根据 `business_id` 更新或创建一个源记录。
        此方法主要操作 th_content 和 th_sources 表。
        """
        with self.transaction() as cursor:
            # 步骤 1: 查找或创建内容记录 (`th_content`)
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
                logger.debug(f"创建了新的内容记录, content_id={content_id}")

            # 步骤 2: 使用 UPSERT 语法高效地更新或创建来源记录 (`th_sources`)
            sql = """
                INSERT INTO th_sources (business_id, content_id, context_hash, last_seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(business_id) DO UPDATE SET
                    content_id = excluded.content_id,
                    context_hash = excluded.context_hash,
                    last_seen_at = excluded.last_seen_at;
            """
            now = datetime.now(timezone.utc)
            cursor.execute(sql, (business_id, content_id, context_hash, now))

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
        """以流式方式获取待翻译的内容批次。
        实现了“先锁定后获取详情”的模式以防止并发冲突。
        现在，锁定事务与数据获取/yield分离。
        """
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
            update_params = [TranslationStatus.TRANSLATING.value, now] + translation_ids
            cursor.execute(update_sql, update_params)
        
        # 事务已提交，现在在事务外部获取 ContentItem 详细信息
        for i in range(0, len(translation_ids), batch_size):
            batch_ids = translation_ids[i : i + batch_size]
            get_details_sql = f"""
                SELECT tr.content_id, c.value, tr.context_hash
                FROM th_translations tr
                JOIN th_content c ON tr.content_id = c.id
                WHERE tr.id IN ({','.join('?' for _ in batch_ids)})
            """
            # 核心修正：直接获取游标，不再使用 with 语句
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
        logger.info(f"准备保存 {len(results)} 条翻译结果...")

        update_params_list = []
        for res in results:
            content_id = self._get_content_id_from_value(res.original_content)
            if content_id is None:
                logger.error(f"无法为原始内容 '{res.original_content}' 找到 content_id，跳过保存此翻译结果。")
                continue

            update_params_list.append(
                {
                    "status": res.status.value,
                    "translation_content": res.translated_content,
                    "engine": res.engine,
                    "last_updated_at": datetime.now(timezone.utc),
                    "content_id": content_id,
                    "lang_code": res.target_lang,
                    "context_hash": res.context_hash,
                }
            )

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
            if update_params_list:
                cursor.executemany(update_sql, update_params_list)
                logger.info(f"成功更新了 {cursor.rowcount} 条翻译记录。")

    def _get_content_id_from_value(self, value: str) -> Optional[int]:
        """辅助方法，用于在 save_translations 中查找 content_id。"""
        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM th_content WHERE value = ?", (value,))
        row = cursor.fetchone()
        return row["id"] if row else None

    def get_translation(
        self, text_content: str, target_lang: str, context: Optional[Dict[str, Any]] = None
    ) -> Optional[TranslationResult]:
        """根据文本内容、目标语言和上下文，从数据库中获取已翻译的结果。
        用于缓存命中查询。
        """
        from trans_hub.utils import get_context_hash as _get_context_hash_util
        context_hash_for_query = _get_context_hash_util(context)

        # 核心修正：直接获取游标，不再使用 with 语句
        cursor = self.connection.cursor()
        try:
            # 步骤 1: 查找内容 ID
            cursor.execute("SELECT id FROM th_content WHERE value = ?", (text_content,))
            content_row = cursor.fetchone()
            if not content_row:
                logger.debug(f"在 th_content 中未找到文本 '{text_content[:20]}...'。")
                return None
            content_id = content_row["id"]

            # 步骤 2: 查找对应的翻译记录
            query_sql = """
                SELECT
                    tr.translation_content,
                    tr.status,
                    tr.engine,
                    tr.last_updated_at
                FROM th_translations tr
                WHERE tr.content_id = ?
                  AND tr.lang_code = ?
                  AND tr.context_hash = ?
                  AND tr.status = ? -- 只查询已翻译的记录
            """
            cursor.execute(
                query_sql,
                (content_id, target_lang, context_hash_for_query, TranslationStatus.TRANSLATED.value)
            )
            translation_row = cursor.fetchone()

            if translation_row:
                # 缓存命中时，尝试从 th_sources 获取 business_id
                retrieved_business_id = self.get_business_id_for_content(
                    content_id=content_id, context_hash=context_hash_for_query
                )
                
                return TranslationResult(
                    original_content=text_content,
                    translated_content=translation_row["translation_content"],
                    target_lang=target_lang,
                    status=TranslationStatus.TRANSLATED,
                    engine=translation_row["engine"],
                    from_cache=True, # 明确标记来自缓存
                    business_id=retrieved_business_id, # 从 th_sources 获取
                    context_hash=context_hash_for_query,
                )
            logger.debug(f"未找到已翻译的记录：content_id={content_id}, lang_code={target_lang}, context_hash={context_hash_for_query}")
            return None
        finally:
            # 在这里可以显式关闭游标，但对于单次查询通常不是必需的，连接关闭时会自动处理
            # cursor.close()
            pass
    
    def get_business_id_for_content(self, content_id: int, context_hash: str) -> Optional[str]:
        """根据 content_id 和 context_hash 从 th_sources 表获取 business_id。"""
        # 核心修正：直接获取游标，不再使用 with 语句
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT business_id FROM th_sources
                WHERE content_id = ? AND context_hash = ?
                """,
                (content_id, context_hash)
            )
            row = cursor.fetchone()
            return row["business_id"] if row else None
        finally:
            # cursor.close()
            pass

    def garbage_collect(self, retention_days: int, dry_run: bool = False) -> dict:
        """执行垃圾回收，清理过时和孤立的数据。"""
        if retention_days < 0:
            raise ValueError("retention_days 必须是非负数。")

        cutoff_datetime = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cutoff_str = cutoff_datetime.isoformat()

        stats = {"deleted_sources": 0, "deleted_content": 0}

        logger.info(
            f"开始垃圾回收 (retention_days={retention_days}, dry_run={dry_run}). "
            f"截止时间: {cutoff_str}"
        )

        with self.transaction() as cursor:
            # --- 阶段 1: 清理过时的 th_sources 记录 ---
            select_expired_sources_sql = (
                "SELECT COUNT(*) FROM th_sources WHERE last_seen_at < ?"
            )
            cursor.execute(select_expired_sources_sql, (cutoff_str,))
            expired_sources_count = cursor.fetchone()[0]
            stats["deleted_sources"] = expired_sources_count

            if not dry_run and expired_sources_count > 0:
                logger.info(f"准备删除 {expired_sources_count} 条过时的源记录...")
                delete_expired_sources_sql = (
                    "DELETE FROM th_sources WHERE last_seen_at < ?"
                )
                cursor.execute(delete_expired_sources_sql, (cutoff_str,))
                assert cursor.rowcount == expired_sources_count
                logger.info("过时的源记录已删除。")
            else:
                logger.info(f"发现 {expired_sources_count} 条可删除的过时源记录 (dry_run)。")

            # --- 阶段 2: 清理孤立的 th_content 记录 ---
            select_orphan_content_sql = """
                SELECT COUNT(c.id)
                FROM th_content c
                WHERE
                    c.created_at < ?
                    AND NOT EXISTS (SELECT 1 FROM th_sources s WHERE s.content_id = c.id)
                    AND NOT EXISTS (SELECT 1 FROM th_translations tr WHERE tr.content_id = c.id)
            """
            cursor.execute(select_orphan_content_sql, (cutoff_str,))
            orphan_content_count = cursor.fetchone()[0]
            stats["deleted_content"] = orphan_content_count

            if not dry_run and orphan_content_count > 0:
                logger.info(f"准备删除 {orphan_content_count} 条孤立的内容记录...")
                delete_orphan_content_sql = """
                    DELETE FROM th_content
                    WHERE id IN (
                        SELECT c.id
                        FROM th_content c
                        WHERE
                            c.created_at < ?
                            AND NOT EXISTS (SELECT 1 FROM th_sources s WHERE s.content_id = c.id)
                            AND NOT EXISTS (SELECT 1 FROM th_translations tr WHERE tr.content_id = c.id)
                    )
                """
                cursor.execute(delete_orphan_content_sql, (cutoff_str,))
                assert cursor.rowcount == orphan_content_count
                logger.info("孤立的内容记录已删除。")
            else:
                logger.info(f"发现 {orphan_content_count} 条可删除的孤立内容记录 (dry_run)。")

        logger.info(f"垃圾回收完成。统计: {stats}")
        return stats

    def close(self) -> None:
        """关闭数据库连接，释放资源。"""
        if self._conn:
            logger.info("正在关闭数据库连接...")
            self._conn.close()
            self._conn = None


# ==============================================================================
#  模块自测试代码 (v0.1)
# ==============================================================================
if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from trans_hub.utils import get_context_hash

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("pydantic").setLevel(logging.INFO)

    DB_FILE = "transhub_test.db"

    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    from trans_hub.db.schema_manager import apply_migrations

    apply_migrations(DB_FILE)

    handler = DefaultPersistenceHandler(DB_FILE)

    try:
        print("\n" + "=" * 20 + " 步骤 1: 准备数据 " + "=" * 20)
        handler.update_or_create_source(
            text_content="hello", business_id="ui.login.welcome", context_hash=get_context_hash(None)
        )
        handler.update_or_create_source(
            text_content="world", business_id="ui.home.title", context_hash=get_context_hash({"k": "v"})
        )

        with handler.transaction() as cursor:
            # content_id=1 ('hello') 请求翻译成德语
            cursor.execute(
                """
                INSERT INTO th_translations (content_id, lang_code, status, engine_version, context_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (1, 'de', TranslationStatus.PENDING.value, 'n/a', get_context_hash(None))
            )
            # content_id=2 ('world') 请求翻译成德语 (带上下文)
            cursor.execute(
                """
                INSERT INTO th_translations (content_id, lang_code, context_hash, status, engine_version)
                VALUES (?, ?, ?, ?, ?)
                """,
                (2, 'de', get_context_hash({"k": "v"}), TranslationStatus.PENDING.value, 'n/a')
            )
        print("数据准备完成。")

        print("\n" + "=" * 20 + " 步骤 2: 获取任务 " + "=" * 20)
        tasks_generator = handler.stream_translatable_items(
            lang_code="de", statuses=[TranslationStatus.PENDING], batch_size=5
        )
        all_tasks = next(tasks_generator, [])
        print(f"获取到 {len(all_tasks)} 个任务: {all_tasks}")
        assert len(all_tasks) == 2, "应该获取到2个德语任务"
        assert all_tasks[0].value == "hello"
        assert all_tasks[0].context_hash == get_context_hash(None)
        assert all_tasks[1].value == "world"
        assert all_tasks[1].context_hash == get_context_hash({"k": "v"})

        print("\n" + "=" * 20 + " 步骤 3: 模拟翻译并保存结果 " + "=" * 20)
        mock_results = [
            TranslationResult(
                original_content="hello",
                translated_content="Hallo",
                target_lang="de",
                status=TranslationStatus.TRANSLATED,
                engine="mock_engine",
                from_cache=False,
                business_id="ui.login.welcome",
                context_hash=get_context_hash(None),
            ),
            TranslationResult(
                original_content="world",
                translated_content=None,
                target_lang="de",
                status=TranslationStatus.FAILED,
                engine="mock_engine",
                error="Simulated API error",
                from_cache=False,
                business_id="ui.home.title",
                context_hash=get_context_hash({"k": "v"}),
            ),
        ]

        handler.save_translations(mock_results)

        print("\n" + "=" * 20 + " 步骤 4: 验证最终状态 " + "=" * 20)
        with handler.transaction() as cursor:
            cursor.execute(
                "SELECT * FROM th_translations WHERE content_id = 1 AND lang_code = 'de'"
            )
            hello_translation = dict(cursor.fetchone())
            print(f"  > 'hello' 的翻译记录: {hello_translation}")
            assert hello_translation["status"] == "TRANSLATED"
            assert hello_translation["translation_content"] == "Hallo"
            assert hello_translation["engine"] == "mock_engine"

            cursor.execute(
                "SELECT * FROM th_translations WHERE content_id = 2 AND lang_code = 'de'"
            )
            world_translation = dict(cursor.fetchone())
            print(f"  > 'world' 的翻译记录: {world_translation}")
            assert world_translation["status"] == "FAILED"
            assert world_translation["translation_content"] is None

        print("\n" + "=" * 20 + " 步骤 5: 验证 get_translation (缓存查询) " + "=" * 20)
        cached_hello = handler.get_translation("hello", "de", None)
        print(f"  > 缓存查询 'hello' 结果: {cached_hello}")
        assert cached_hello is not None
        assert cached_hello.translated_content == "Hallo"
        assert cached_hello.from_cache is True
        assert cached_hello.business_id == "ui.login.welcome"

        cached_world = handler.get_translation("world", "de", {"k": "v"})
        print(f"  > 缓存查询 'world' 结果: {cached_world}")
        assert cached_world is None 

        print("\n所有验证成功！DefaultPersistenceHandler (v1.0 第四次修正版) 已与最终版文档对齐并修复所有问题！")

    except Exception:
        logging.error("测试过程中发生异常", exc_info=True)
    finally:
        handler.close()
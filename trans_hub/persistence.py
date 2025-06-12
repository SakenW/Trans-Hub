"""trans_hub/persistence.py (v0.1)

本模块提供了持久化处理器的具体实现。
它实现了 `PersistenceHandler` 接口，并负责与数据库进行所有交互。
此版本已完全根据最终版文档的数据库 Schema 和 DTOs 重写。
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator, List, Optional

import structlog

# [变更] 导入已更新的 DTOs
from trans_hub.interfaces import PersistenceHandler
from trans_hub.types import (
    ContentItem,
    SourceUpdateResult,
    TranslationResult,
    TranslationStatus,
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
            # `check_same_thread=False` 允许在多线程中共享此连接对象。
            # 这在我们未来的异步或多线程应用中可能是必要的。
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)

            # `row_factory = sqlite3.Row` 是一个非常有用的设置。
            # 它让查询结果可以像字典一样通过列名访问（e.g., row['id']），
            # 而不是只能通过索引（e.g., row[0]），极大地提高了代码的可读性。
            self._conn.row_factory = sqlite3.Row

            # 再次确保关键的 PRAGMA 指令已启用。
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute("PRAGMA journal_mode = WAL;")
        except sqlite3.Error as e:
            logger.error(f"连接数据库失败: {e}", exc_info=True)
            raise

    @property
    def connection(self) -> sqlite3.Connection:
        """提供一个安全的属性来访问连接对象，确保它不是 None。"""
        if self._conn is None:
            # 这是一个防御性编程，如果连接丢失，程序应该快速失败。
            raise RuntimeError("数据库未连接。")
        return self._conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """一个提供原子事务的上下文管理器。
        这是保证数据一致性的核心工具。使用 `with self.transaction() as cursor:`
        可以确保代码块内的所有数据库操作要么全部成功提交，要么在发生任何异常时全部回滚。
        """
        cursor = self.connection.cursor()
        try:
            # 开始一个事务
            cursor.execute("BEGIN;")
            yield cursor
            # 如果 `with` 块成功执行完毕，提交事务
            self.connection.commit()
        except Exception as e:
            # 如果 `with` 块中发生任何异常，回滚所有更改
            logger.error(f"事务执行失败，正在回滚: {e}", exc_info=True)
            self.connection.rollback()
            raise  # 重新抛出异常，让上层代码知道操作失败

    def update_or_create_source(
        self, text_content: str, business_id: str, context_hash: Optional[str]
    ) -> SourceUpdateResult:
        """[变更] 根据 `business_id` 更新或创建一个源记录。"""
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
            # UPSERT (INSERT ON CONFLICT) 是处理“如果存在则更新，否则插入”场景的最高效方式。
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
        """[变更] 以流式方式获取待翻译的内容批次。
        实现了“先锁定后获取详情”的模式以防止并发冲突。
        """
        status_values = tuple(s.value for s in statuses)
        limit_clause = f"LIMIT {limit}" if limit is not None else ""

        # 步骤 1: 在一个事务中，找到所有符合条件的任务ID，并立即将其状态更新为 'TRANSLATING'。
        # 这是一个原子操作，确保多个进程不会获取到相同的任务。
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

        # 步骤 2: 事务已提交，锁已释放。现在在事务外安全地分批获取详细信息。
        # 这样做可以减少数据库长事务的持有时间。
        for i in range(0, len(translation_ids), batch_size):
            batch_ids = translation_ids[i : i + batch_size]
            get_details_sql = f"""
                SELECT c.id as content_id, c.value, tr.context_hash
                FROM th_content c
                JOIN th_translations tr ON c.id = tr.content_id
                WHERE tr.id IN ({','.join('?' for _ in batch_ids)})
            """
            # 使用一个新的游标执行只读查询
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
        """[变更] 将一批翻译结果保存到数据库中。"""
        if not results:
            return
        logger.info(f"准备保存 {len(results)} 条翻译结果...")

        # 将 `TranslationResult` DTO 转换为适合数据库批量更新的参数字典列表。
        update_params_list = []
        for res in results:
            # 注意，这里我们依赖 Coordinator 确保 `TranslationResult` 包含所有必要信息。
            update_params_list.append(
                {
                    "status": res.status.value,
                    "translation_content": res.translated_content,
                    "engine": res.engine,
                    "last_updated_at": datetime.now(timezone.utc),
                    "original_content": res.original_content,  # 用于查找 content_id
                    "lang_code": res.target_lang,
                    "context_hash": res.context_hash,
                }
            )

        with self.transaction() as cursor:
            # 步骤 1: 在事务内，根据 `original_content` 批量查找 `content_id`。
            # 这是必要的，因为 `th_translations` 表是通过 `content_id` 关联的。
            content_map = {}
            all_contents = {p["original_content"] for p in update_params_list}
            placeholders = ",".join("?" for _ in all_contents)
            cursor.execute(
                f"SELECT id, value FROM th_content WHERE value IN ({placeholders})",
                list(all_contents),
            )
            for row in cursor.fetchall():
                content_map[row["value"]] = row["id"]

            for params in update_params_list:
                params["content_id"] = content_map.get(params["original_content"])

            # 步骤 2: 批量更新 `th_translations` 表。
            # `executemany` 是 SQLite 进行批量操作的最高效方式。
            update_sql = """
                UPDATE th_translations SET
                    status = :status,
                    translation_content = :translation_content,
                    engine = :engine,
                    last_updated_at = :last_updated_at
                WHERE content_id = :content_id
                  AND lang_code = :lang_code
                  AND context_hash IS :context_hash
                  AND status = 'TRANSLATING' -- 增加状态检查，避免覆盖已批准或已失败的记录
            """
            # 过滤掉那些没找到 content_id 的记录
            updatable_params = [p for p in update_params_list if p.get("content_id")]
            if updatable_params:
                cursor.executemany(update_sql, updatable_params)
                logger.info(f"成功更新了 {cursor.rowcount} 条翻译记录。")

    # 在 trans_hub/persistence.py 的 DefaultPersistenceHandler 类中添加

    def garbage_collect(self, retention_days: int, dry_run: bool = False) -> dict:
        """执行垃圾回收，清理过时和孤立的数据。

        Args:
        ----
            retention_days: 数据保留天数。早于这个天数的记录将被视为过时。
            dry_run: 如果为 True，则只查询将要删除的记录数量，而不执行实际删除。

        Returns:
        -------
            一个字典，包含清理结果的统计信息，
            例如: {"deleted_sources": 10, "deleted_content": 5}。

        """
        if retention_days < 0:
            raise ValueError("retention_days 必须是非负数。")

        # 计算截止时间点
        cutoff_datetime = datetime.now(timezone.utc) - timedelta(days=retention_days)
        # SQLite 需要一个特定的字符串格式
        cutoff_str = cutoff_datetime.isoformat()

        stats = {"deleted_sources": 0, "deleted_content": 0}

        logger.info(
            f"开始垃圾回收 (retention_days={retention_days}, dry_run={dry_run}). "
            f"截止时间: {cutoff_str}"
        )

        with self.transaction() as cursor:
            # --- 阶段 1: 清理过时的 th_sources 记录 ---
            # 查询将要被删除的源记录数量
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
                # 确认删除的数量
                assert cursor.rowcount == expired_sources_count
                logger.info("过时的源记录已删除。")
            else:
                logger.info(f"发现 {expired_sources_count} 条可删除的过时源记录 (dry_run)。")

            # --- 阶段 2: 清理孤立的 th_content 记录 ---
            # 一个 `th_content` 记录是孤立的，当且仅当：
            # 1. 它不被任何 `th_sources` 记录所引用。
            # 2. 它不被任何 `th_translations` 记录所引用。
            # 3. 它的创建时间早于保留期限（可选，防止误删刚创建但还未被引用的内容）

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
#  - 当直接运行此文件时 (python -m trans_hub.persistence)，会执行此部分。
#  - 用于快速验证本模块核心功能的正确性。
# ==============================================================================
if __name__ == "__main__":
    import os

    # --- 基本配置 ---
    logging.basicConfig(
        level=logging.DEBUG,
        # 格式化日志，包含时间、模块名、日志级别和消息
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Pydantic 在 DEBUG 级别下会产生大量校验日志，我们将其调高以保持输出整洁。
    logging.getLogger("pydantic").setLevel(logging.INFO)

    DB_FILE = "transhub_test.db"

    # --- 步骤 0: 准备一个干净的数据库 ---
    # 确保每次测试都在一个全新的、可预测的环境中开始。
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    from trans_hub.db.schema_manager import apply_migrations

    # 应用最新的 schema 定义
    apply_migrations(DB_FILE)

    # --- 初始化处理器 ---
    handler = DefaultPersistenceHandler(DB_FILE)

    try:
        # === 步骤 1: 创建源数据和待办任务 ===
        print("\n" + "=" * 20 + " 步骤 1: 准备数据 " + "=" * 20)
        # 使用新文档推荐的 business_id 命名规范
        handler.update_or_create_source(
            text_content="hello", business_id="ui.login.welcome", context_hash=None
        )
        handler.update_or_create_source(
            text_content="world", business_id="ui.home.title", context_hash="c1"
        )

        # 模拟 Coordinator 创建翻译任务
        with handler.transaction() as cursor:
            # content_id=1 ('hello') 请求翻译成德语
            cursor.execute(
                "INSERT INTO th_translations (content_id, lang_code, status, engine_version) VALUES (1, 'de', 'PENDING', 'n/a')"
            )
            # content_id=2 ('world') 请求翻译成德语 (带上下文)
            cursor.execute(
                "INSERT INTO th_translations (content_id, lang_code, context_hash, status, engine_version) VALUES (2, 'de', 'c1', 'PENDING', 'n/a')"
            )
        print("数据准备完成。")

        # === 步骤 2: 获取待办任务 ===
        print("\n" + "=" * 20 + " 步骤 2: 获取任务 " + "=" * 20)
        tasks_generator = handler.stream_translatable_items(
            lang_code="de", statuses=[TranslationStatus.PENDING], batch_size=5
        )
        # 从生成器中获取第一个（也是唯一一个）批次
        all_tasks = next(tasks_generator, [])
        print(f"获取到 {len(all_tasks)} 个任务: {all_tasks}")
        assert len(all_tasks) == 2, "应该获取到2个德语任务"
        # 验证获取到的内容是否正确
        assert all_tasks[0].value == "hello"
        assert all_tasks[1].value == "world"

        # === 步骤 3: 模拟翻译并保存结果 ===
        print("\n" + "=" * 20 + " 步骤 3: 保存翻译结果 " + "=" * 20)

        # 模拟翻译结果：一个成功，一个失败
        # DTO 使用了新的字段名 original_content, translated_content
        mock_results = [
            TranslationResult(
                original_content="hello",
                translated_content="Hallo",
                target_lang="de",
                status=TranslationStatus.TRANSLATED,
                engine="mock_engine",
                from_cache=False,
                business_id="ui.login.welcome",  # 传递回去以供参考
                context_hash=None,
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
                context_hash="c1",
            ),
        ]

        handler.save_translations(mock_results)

        # === 步骤 4: 验证最终结果 ===
        print("\n" + "=" * 20 + " 步骤 4: 验证最终状态 " + "=" * 20)

        with handler.transaction() as cursor:
            # 验证 "hello" 的翻译
            cursor.execute(
                "SELECT * FROM th_translations WHERE content_id = 1 AND lang_code = 'de'"
            )
            hello_translation = dict(cursor.fetchone())
            print(f"  > 'hello' 的翻译记录: {hello_translation}")
            assert hello_translation["status"] == "TRANSLATED"
            assert hello_translation["translation_content"] == "Hallo"
            assert hello_translation["engine"] == "mock_engine"

            # 验证 "world" 的翻译
            cursor.execute(
                "SELECT * FROM th_translations WHERE content_id = 2 AND lang_code = 'de'"
            )
            world_translation = dict(cursor.fetchone())
            print(f"  > 'world' 的翻译记录: {world_translation}")
            assert world_translation["status"] == "FAILED"
            assert world_translation["translation_content"] is None

        print("\n所有验证成功！DefaultPersistenceHandler (v0.1) 已与最终版文档完全对齐！")

    except Exception:
        # 使用 exc_info=True 会打印出完整的堆栈跟踪，便于调试
        logging.error("测试过程中发生异常", exc_info=True)
    finally:
        # --- 确保连接总是被关闭 ---
        handler.close()

"""
trans_hub/persistence.py

本模块提供了持久化处理器的具体实现。
它实现了 PersistenceHandler 和 AsyncPersistenceHandler 接口，
并负责与数据库进行所有交互。
"""
import os
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, List, Optional

from trans_hub.interfaces import PersistenceHandler
from trans_hub.types import SourceUpdateResult, TextItem, TranslationResult, TranslationStatus

logger = logging.getLogger(__name__)


class DefaultPersistenceHandler(PersistenceHandler):
    """
    使用标准库 `sqlite3` 实现的同步持久化处理器。
    """

    def __init__(self, db_path: str):
        """
        初始化处理器。

        Args:
            db_path: SQLite 数据库文件的路径。
        """
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        # 在这里连接数据库，确保应用生命周期内复用连接
        self._connect()

    def _connect(self):
        """建立数据库连接并进行基本配置。"""
        try:
            logger.info(f"正在连接到数据库: {self.db_path}")
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # 配置连接以返回字典形式的行，方便操作
            self._conn.row_factory = sqlite3.Row
            # 启用外键约束和WAL模式
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute("PRAGMA journal_mode = WAL;")
            logger.info("数据库连接成功并已配置。")
        except sqlite3.Error as e:
            logger.error(f"连接数据库失败: {e}")
            raise

    @property
    def connection(self) -> sqlite3.Connection:
        """获取数据库连接的属性，确保连接存在。"""
        if self._conn is None:
            raise RuntimeError("数据库未连接。请先调用 _connect()。")
        return self._conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """
        一个提供原子事务的上下文管理器。
        它能确保在代码块中的所有数据库操作要么全部成功，要么全部回滚。
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute("BEGIN;")
            yield cursor
            self.connection.commit()
            logger.debug("事务成功提交。")
        except Exception as e:
            logger.error(f"事务执行失败，正在回滚: {e}")
            self.connection.rollback()
            raise

    def update_or_create_source(
        self, text: str, business_id: str, context_hash: Optional[str]
    ) -> SourceUpdateResult:
        """
        根据 business_id 更新或创建一个源记录。
        这是项目中一个核心的、复杂的事务性操作。
        """
        with self.transaction() as cursor:
            # 步骤 1: 查找或创建文本记录 (th_texts)
            cursor.execute("SELECT id FROM th_texts WHERE text_content = ?", (text,))
            text_row = cursor.fetchone()

            is_newly_created = False
            if text_row:
                text_id = text_row["id"]
            else:
                # 文本不存在，插入新文本
                cursor.execute("INSERT INTO th_texts (text_content) VALUES (?)", (text,))
                text_id = cursor.lastrowid
                is_newly_created = True
                logger.info(f"创建了新的文本记录, id={text_id}")

            # 步骤 2: 处理业务来源记录 (th_sources)
            # 使用 UPSERT (INSERT ON CONFLICT) 语法，这是 SQLite 3.24.0+ 的特性，非常高效
            # 它会尝试插入，如果 business_id 冲突，则执行 UPDATE 部分
            sql = """
                INSERT INTO th_sources (business_id, text_id, context_hash, last_seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(business_id) DO UPDATE SET
                    text_id = excluded.text_id,
                    context_hash = excluded.context_hash,
                    last_seen_at = excluded.last_seen_at;
            """
            now = datetime.now(timezone.utc)
            cursor.execute(sql, (business_id, text_id, context_hash, now))
            logger.debug(f"更新或创建了来源记录, business_id='{business_id}', text_id={text_id}")

            return SourceUpdateResult(
                text_id=text_id, is_newly_created=is_newly_created
            )


    def stream_translatable_items(
        self,
        lang_code: str,
        statuses: List[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> Generator[List[TextItem], None, None]:
        """
        以流式方式获取待翻译的文本批次。

        此方法实现了防止并发冲突的关键逻辑：
        1. 在一个事务中，首先查询出符合条件的、待翻译的条目ID。
        2. 立即将这些条目的状态更新为 'TRANSLATING'，并将它们“锁定”。
        3. 提交事务，释放锁。
        4. 然后，根据已锁定的ID，查询完整的文本内容并打包成批次返回。
        
        这种 "SELECT, UPDATE, then SELECT details" 的模式可以有效避免
        多个工作进程获取到相同的任务。
        """
        logger.info(
            f"开始流式获取待翻译项: lang='{lang_code}', "
            f"statuses={[s.value for s in statuses]}, batch_size={batch_size}"
        )
        
        # 将枚举状态列表转换为字符串元组，以供 SQL 查询使用
        status_values = tuple(s.value for s in statuses)
        
        # 限制获取的总量
        limit_clause = f"LIMIT {limit}" if limit is not None else ""

        try:
            with self.transaction() as cursor:
                # 步骤 1: 查询出符合条件的、唯一的 text_id 列表
                # 我们需要在 th_texts 和 th_translations 之间进行连接
                # 并且确保对于给定的语言，还没有 TRANSLATED 或 APPROVED 的版本
                # (这里的逻辑可以根据具体需求进一步细化)
                
                # 首先，找到所有需要翻译的 text_id 和 context_hash 组合
                # 这里的逻辑是：一个 (text, lang, context) 组合如果没有任何翻译记录，
                # 或者所有记录的状态都在 'PENDING' 或 'FAILED' 状态，那么它就是需要翻译的。
                
                # 为了简化，我们先假设一旦有 business_id 请求，就会自动创建 PENDING 记录。
                # 所以我们只需要查找 PENDING 或 FAILED (可重试) 的记录。
                
                # 简化后的逻辑：直接在 th_translations 表中查找
                find_ids_sql = f"""
                    SELECT id FROM th_translations
                    WHERE lang_code = ? AND status IN ({','.join('?' for _ in status_values)})
                    ORDER BY last_updated_at ASC
                    {limit_clause}
                """
                
                params = [lang_code] + list(status_values)
                cursor.execute(find_ids_sql, params)
                translation_ids = [row[0] for row in cursor.fetchall()]

                if not translation_ids:
                    logger.info("没有找到待翻译的条目。")
                    return  # 提前退出生成器

                logger.info(f"发现了 {len(translation_ids)} 个待翻译条目，正在锁定...")

                # 步骤 2: 立即将这些条目的状态更新为 'TRANSLATING' 来锁定它们
                update_sql = f"""
                    UPDATE th_translations
                    SET status = ?, last_updated_at = ?
                    WHERE id IN ({','.join('?' for _ in translation_ids)})
                """
                now = datetime.now(timezone.utc)
                update_params = [TranslationStatus.TRANSLATING.value, now] + translation_ids
                cursor.execute(update_sql, update_params)
                logger.info(f"成功将 {cursor.rowcount} 个条目的状态更新为 'TRANSLATING'。")
            
            # 步骤 3: 事务已提交，锁已释放。现在安全地获取详细信息。
            # 我们分批次获取，避免一次性加载过多内容到内存。
            for i in range(0, len(translation_ids), batch_size):
                batch_ids = translation_ids[i:i + batch_size]
                
                get_details_sql = f"""
                    SELECT t.id as text_id, t.text_content, tr.context_hash
                    FROM th_texts t
                    JOIN th_translations tr ON t.id = tr.text_id
                    WHERE tr.id IN ({','.join('?' for _ in batch_ids)})
                """

                # 这里我们可以在事务外执行只读查询
                read_cursor = self.connection.cursor()
                read_cursor.execute(get_details_sql, batch_ids)
                
                batch_items = [
                    TextItem(
                        text_id=row['text_id'],
                        text_content=row['text_content'],
                        context_hash=row['context_hash'],
                    )
                    for row in read_cursor.fetchall()
                ]
                
                if batch_items:
                    logger.debug(f"产出一个批次，包含 {len(batch_items)} 个条目。")
                    yield batch_items

        except sqlite3.Error as e:
            logger.error(f"流式获取待翻译项时发生数据库错误: {e}")
            raise


    def save_translations(self, results: List[TranslationResult]) -> None:
        """
        将一批翻译结果保存到数据库中。

        此方法在一个单独的事务中批量更新所有翻译记录。
        它能处理成功和失败两种情况。
        """
        if not results:
            return

        logger.info(f"准备保存 {len(results)} 条翻译结果...")

        # 我们需要一种方法将 TranslationResult 映射回数据库中的正确记录。
        # 最可靠的方式是通过 (text_content, lang_code, context_hash) 的组合来定位。
        # 首先，我们需要获取所有相关文本的 text_id。
        
        text_content_to_id = {}
        all_text_contents = {res.original_text for res in results}
        
        # 在一个事务外查询所有 text_id，减少事务锁定时间
        try:
            with self.transaction() as cursor:
                # 使用参数化查询来避免SQL注入
                placeholders = ','.join('?' for _ in all_text_contents)
                sql = f"SELECT id, text_content FROM th_texts WHERE text_content IN ({placeholders})"
                cursor.execute(sql, list(all_text_contents))
                for row in cursor.fetchall():
                    text_content_to_id[row['text_content']] = row['id']
        except sqlite3.Error as e:
            logger.error(f"保存翻译前查询 text_id 失败: {e}")
            raise

        # 准备批量更新的数据
        update_params_list = []
        for res in results:
            text_id = text_content_to_id.get(res.original_text)
            if text_id is None:
                logger.warning(
                    f"在数据库中找不到文本 '{res.original_text}' 的记录，跳过保存其翻译结果。"
                )
                continue

            # 对于 context_hash 为 None 的情况，SQL需要处理 IS NULL
            # 但在这里，我们可以通过唯一的 (text_id, lang_code, context_hash) 来定位记录
            # TODO: context_hash 需要从 TranslationResult 中获取，我们先假设它存在。
            # 为了简化，我们先假设可以唯一确定。在Coordinator中需要确保这一点。
            
            # 我们直接使用 (text_id, lang_code) 来定位要更新的记录
            # 注意：这在有多个不同 context 的翻译时可能不准确，
            # 更好的方法是让 TranslationResult 携带 context_hash。
            # 我们暂时简化处理。
            
            params = {
                "status": res.status.value,
                "translation_content": res.translated_text,
                "engine": res.engine,
                "last_updated_at": datetime.now(timezone.utc),
                "text_id": text_id,
                "lang_code": res.target_lang
            }
            update_params_list.append(params)

        # 在一个事务中执行所有更新
        try:
            with self.transaction() as cursor:
                sql = """
                    UPDATE th_translations SET
                        status = :status,
                        translation_content = :translation_content,
                        engine = :engine,
                        last_updated_at = :last_updated_at
                    WHERE text_id = :text_id AND lang_code = :lang_code AND status = 'TRANSLATING'
                """
                # 使用 executemany 进行高效的批量更新
                cursor.executemany(sql, update_params_list)
                logger.info(f"成功保存了 {cursor.rowcount} 条翻译结果。")

        except sqlite3.Error as e:
            logger.error(f"批量保存翻译结果时发生数据库错误: {e}")
            raise

    def garbage_collect(self, retention_days: int) -> dict:
        """
        执行垃圾回收。
        (此方法将在下一步实现)
        """
        # TODO: 实现此方法的逻辑
        return {} # 临时的空实现

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn:
            logger.info("正在关闭数据库连接...")
            self._conn.close()
            self._conn = None
            logger.info("数据库连接已关闭。")


if __name__ == "__main__":
    # --- 基本配置 ---
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("pydantic").setLevel(logging.INFO)

    DB_FILE = "transhub_test.db"
    
    # --- 准备一个干净的数据库 ---
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    
    from trans_hub.db.schema_manager import apply_migrations
    apply_migrations(DB_FILE)

    # --- 初始化处理器 ---
    handler = DefaultPersistenceHandler(DB_FILE)

    try:
        # === 步骤 1: 创建源数据和待办任务 ===
        print("\n" + "=" * 20 + " 步骤 1: 准备数据 " + "=" * 20)
        handler.update_or_create_source(text="hello", business_id="login:welcome", context_hash=None)
        handler.update_or_create_source(text="world", business_id="home:title", context_hash="c1")
        
        with handler.transaction() as cursor:
            cursor.execute("INSERT INTO th_translations (text_id, lang_code, status, engine_version) VALUES (1, 'de', 'PENDING', 'n/a')")
            cursor.execute("INSERT INTO th_translations (text_id, lang_code, context_hash, status, engine_version) VALUES (2, 'de', 'c1', 'PENDING', 'n/a')")
        print("数据准备完成。")

        # === 步骤 2: 获取待办任务 ===
        print("\n" + "=" * 20 + " 步骤 2: 获取任务 " + "=" * 20)
        tasks_generator = handler.stream_translatable_items(
            lang_code="de", statuses=[TranslationStatus.PENDING], batch_size=5
        )
        all_tasks = next(tasks_generator, [])
        print(f"获取到 {len(all_tasks)} 个任务: {all_tasks}")
        assert len(all_tasks) == 2

        # === 步骤 3: 模拟翻译并保存结果 ===
        print("\n" + "=" * 20 + " 步骤 3: 保存翻译结果 " + "=" * 20)
        
        # 模拟翻译结果：一个成功，一个失败
        mock_results = [
            TranslationResult(
                original_text="hello",
                translated_text="Hallo",
                target_lang="de",
                status=TranslationStatus.TRANSLATED,
                engine="mock_engine",
                from_cache=False,
            ),
            TranslationResult(
                original_text="world",
                translated_text=None,
                target_lang="de",
                status=TranslationStatus.FAILED,
                engine="mock_engine",
                error="Simulated API error",
                from_cache=False,
            ),
        ]
        
        handler.save_translations(mock_results)
        print("翻译结果已保存。")

        # === 步骤 4: 验证最终结果 ===
        print("\n" + "=" * 20 + " 步骤 4: 验证最终状态 " + "=" * 20)
        
        with handler.transaction() as cursor:
            # 验证 "hello" 的翻译
            cursor.execute("SELECT * FROM th_translations WHERE text_id = 1 AND lang_code = 'de'")
            hello_translation = dict(cursor.fetchone())
            print(f"  > 'hello' 的翻译记录: {hello_translation}")
            assert hello_translation["status"] == "TRANSLATED"
            assert hello_translation["translation_content"] == "Hallo"
            assert hello_translation["engine"] == "mock_engine"

            # 验证 "world" 的翻译
            cursor.execute("SELECT * FROM th_translations WHERE text_id = 2 AND lang_code = 'de'")
            world_translation = dict(cursor.fetchone())
            print(f"  > 'world' 的翻译记录: {world_translation}")
            assert world_translation["status"] == "FAILED"
            assert world_translation["translation_content"] is None
            
        print("\n所有验证成功！DefaultPersistenceHandler 已基本完成！")

    except Exception as e:
        logging.error("测试过程中发生异常", exc_info=True)
    finally:
        # --- 关闭连接 ---
        handler.close()
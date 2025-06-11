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
        (此方法将在下一步实现)
        """
        # TODO: 实现此方法的逻辑
        # 关键点：需要先 SELECT ... FOR UPDATE (在SQLite中用事务模拟)，
        # 然后立即 UPDATE 状态为 'TRANSLATING'，最后才 yield 数据。
        yield []  # 临时的空实现

    def save_translations(self, results: List[TranslationResult]) -> None:
        """
        将一批翻译结果保存到数据库中。
        (此方法将在下一步实现)
        """
        # TODO: 实现此方法的逻辑
        pass # 临时的空实现

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


# --- 为了让模块可运行和测试，添加一些简单的调用代码 ---
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    DB_FILE = "transhub_test.db"

    # 在每次运行时，如果旧数据库文件存在，就先删除它
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        logger.info(f"已删除旧的测试数据库: {DB_FILE}")

    # 0. 准备工作：确保数据库和 schema 存在
    from trans_hub.db.schema_manager import apply_migrations
    apply_migrations(DB_FILE)

    # 1. 初始化处理器
    handler = DefaultPersistenceHandler(DB_FILE)

    try:
        # 2. 测试 update_or_create_source
        print("\n--- 第一次请求 'hello' ---")
        res1 = handler.update_or_create_source(
            text="hello", business_id="login_page:welcome_message", context_hash=None
        )
        print(f"结果: {res1}")

        print("\n--- 第二次请求 'hello' (同样 business_id) ---")
        res2 = handler.update_or_create_source(
            text="hello", business_id="login_page:welcome_message", context_hash=None
        )
        print(f"结果: {res2}")
        
        print("\n--- 更新 business_id 关联的文本为 'hello world' ---")
        res3 = handler.update_or_create_source(
            text="hello world", business_id="login_page:welcome_message", context_hash=None
        )
        print(f"结果: {res3}")

    finally:
        # 3. 关闭连接
        handler.close()
# trans_hub/persistence/postgres.py
"""
提供了基于 asyncpg 的 PostgreSQL 持久化实现。

本模块是 `PersistenceHandler` 协议的 PostgreSQL 具体实现，
为 Trans-Hub 提供了高性能、高并发的生产级数据后端。
"""

import asyncio
import json
from typing import Any, AsyncGenerator, Optional

try:
    import asyncpg
    from asyncpg.exceptions import UniqueViolationError
except ImportError:
    asyncpg = None
    UniqueViolationError = None

import structlog

from trans_hub.core.exceptions import DatabaseError
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.core.types import (
    ContentItem,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.utils import get_context_hash

logger = structlog.get_logger(__name__)


class PostgresPersistenceHandler(PersistenceHandler):
    """`PersistenceHandler` 协议的 PostgreSQL 实现。"""

    SUPPORTS_NOTIFICATIONS = True
    NOTIFICATION_CHANNEL = "new_translation_task"

    def __init__(self, dsn: str):
        if asyncpg is None:
            raise ImportError(
                "要使用 PostgresPersistenceHandler, 请安装 'asyncpg' 驱动。"
            )
        self.dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None
        logger.info("PostgreSQL 持久层已配置")

    async def connect(self) -> None:
        """建立与数据库的连接。"""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.dsn)
            logger.info("已连接到 PostgreSQL 数据库")

    async def close(self) -> None:
        """关闭与数据库的连接。"""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("已关闭与 PostgreSQL 数据库的连接")

    def _transaction(self) -> asyncpg.pool.PoolAcquireContext:
        """获取数据库事务连接。"""
        if self._pool is None:
            raise RuntimeError("数据库连接池未初始化")
        return self._pool.acquire()

    # ... 其他方法保持不变 ...

    async def create_pending_translations(
        self,
        content_id: str,
        context_id: Optional[str],
        target_langs: list[str],
        source_lang: Optional[str],
        engine_version: str,
        force_retranslate: bool = False,
    ) -> None:
        """[实现] 为给定的内容和上下文创建待处理的翻译任务。"""
        try:
            async with self._transaction() as conn:
                # v4.0 修复：为 force_retranslate 使用独立的、正确的 SQL 语句
                if force_retranslate:
                    sql = """
INSERT INTO th_translations (
    content_id, context_id, lang_code, source_lang,
    engine_version
)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (content_id, context_id, lang_code) DO UPDATE
SET status = 'PENDING',
    source_lang = EXCLUDED.source_lang,
    engine_version = EXCLUDED.engine_version,
    translation_payload_json = NULL,
    error = NULL,
    last_updated_at = now();
"""
                else:
                    sql = """
INSERT INTO th_translations (
    content_id, context_id, lang_code, source_lang,
    engine_version
)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (content_id, context_id, lang_code) DO NOTHING;
"""

                params = [
                    (content_id, context_id, lang, source_lang, engine_version)
                    for lang in target_langs
                ]
                if params:
                    await conn.executemany(sql, params)
        except (UniqueViolationError, asyncpg.PostgresError) as e:
            raise DatabaseError(f"创建待处理翻译失败: {e}") from e

    async def save_translation_results(
        self,
        results: list[TranslationResult],
    ) -> None:
        if not results:
            return
        params = [
            (
                res.status.value,
                json.dumps(res.translated_payload) if res.translated_payload else None,
                res.engine,
                res.error,
                res.translation_id,
            )
            for res in results
        ]
        sql = """
            UPDATE th_translations
            SET
                status = $1,
                translation_payload_json = $2::jsonb,
                engine = $3,
                error = $4,
                last_updated_at = now()
            WHERE id = $5::uuid AND status = 'TRANSLATING';
        """
        try:
            async with self._transaction() as conn:
                await conn.executemany(sql, params)
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"保存翻译结果失败: {e}") from e

    async def find_translation(
        self,
        business_id: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        context_hash = get_context_hash(context)
        sql = """
            SELECT
                t.id AS translation_id,
                c.source_payload_json,
                t.translation_payload_json,
                t.status,
                t.engine,
                t.error
            FROM th_translations t
            JOIN th_content c ON t.content_id = c.id
            LEFT JOIN th_contexts ctx ON t.context_id = ctx.id
            WHERE c.business_id = $1
              AND t.lang_code = $2
              AND COALESCE(ctx.context_hash, '__GLOBAL__') = $3
            ORDER BY t.last_updated_at DESC
            LIMIT 1;
        """
        try:
            async with self._transaction() as conn:
                row = await conn.fetchrow(sql, business_id, target_lang, context_hash)
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"查找翻译失败: {e}") from e
        if not row:
            return None
        original_payload = json.loads(row["source_payload_json"])
        translated_payload = (
            json.loads(row["translation_payload_json"])
            if row["translation_payload_json"]
            else None
        )
        return TranslationResult(
            translation_id=str(row["translation_id"]),
            business_id=business_id,
            original_payload=original_payload,
            translated_payload=translated_payload,
            target_lang=target_lang,
            status=TranslationStatus(row["status"]),
            engine=row["engine"],
            from_cache=True,
            error=row["error"],
            context_hash=context_hash,
        )

    async def garbage_collect(
        self, retention_days: int, dry_run: bool = False
    ) -> dict[str, int]:
        stats = {"deleted_jobs": 0, "deleted_content": 0, "deleted_contexts": 0}
        cutoff_date_sql = "now() - interval '%s days'" % retention_days
        try:
            async with self._transaction() as conn:
                del_jobs_sql = (
                    f"DELETE FROM th_jobs WHERE last_requested_at < {cutoff_date_sql} "
                    "RETURNING id;"
                )
                if dry_run:
                    del_jobs_sql = (
                        f"SELECT id FROM th_jobs WHERE last_requested_at "
                        f"< {cutoff_date_sql};"
                    )
                deleted_jobs = await conn.fetch(del_jobs_sql)
                stats["deleted_jobs"] = len(deleted_jobs)
                del_content_sql = """
                    DELETE FROM th_content c
                    WHERE NOT EXISTS (SELECT 1 FROM th_jobs j WHERE j.content_id = c.id)
                    RETURNING id;
                """
                if dry_run:
                    del_content_sql = """
                        SELECT id FROM th_content c
                        WHERE NOT EXISTS (
                            SELECT 1 FROM th_jobs j WHERE j.content_id = c.id
                        );
                    """
                deleted_content = await conn.fetch(del_content_sql)
                stats["deleted_content"] = len(deleted_content)
                del_contexts_sql = """
                    DELETE FROM th_contexts ctx
                    WHERE NOT EXISTS (
                        SELECT 1 FROM th_translations t WHERE t.context_id = ctx.id
                    ) RETURNING id;
                """
                if dry_run:
                    del_contexts_sql = """
                        SELECT id FROM th_contexts ctx
                        WHERE NOT EXISTS (
                            SELECT 1 FROM th_translations t
                            WHERE t.context_id = ctx.id
                        );
                    """
                deleted_contexts = await conn.fetch(del_contexts_sql)
                stats["deleted_contexts"] = len(deleted_contexts)
                if dry_run:
                    raise asyncpg.exceptions.RollbackTransactionError("Dry run")
            return stats
        except asyncpg.exceptions.RollbackTransactionError:
            logger.info("垃圾回收 (dry run) 完成，事务已回滚。")
            return stats
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"垃圾回收失败: {e}") from e

    async def move_to_dlq(
        self,
        item: ContentItem,
        target_lang: str,
        error_message: str,
        engine_name: str,
        engine_version: str,
    ) -> None:
        try:
            async with self._transaction() as conn:
                await conn.execute(
                    """
                    INSERT INTO th_dead_letter_queue (
                        translation_id, original_payload_json, context_payload_json,
                        target_lang_code, last_error_message,
                        engine_name, engine_version
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    item.translation_id,
                    json.dumps(item.source_payload),
                    json.dumps(item.context) if item.context else None,
                    target_lang,
                    error_message,
                    engine_name,
                    engine_version,
                )
                await conn.execute(
                    "DELETE FROM th_translations WHERE id = $1", item.translation_id
                )
            logger.info("任务已成功移至死信队列", translation_id=item.translation_id)
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"移动到死信队列失败: {e}") from e

    async def ensure_content_and_context(
        self,
        business_id: str,
        source_payload: dict[str, Any],
        context: Optional[dict[str, Any]],
    ) -> tuple[str, Optional[str]]:
        context_hash = get_context_hash(context)
        try:
            async with self._transaction() as conn:
                # 插入或获取内容ID
                content_sql = """
                    INSERT INTO th_content (business_id, source_payload_json)
                    VALUES ($1, $2)
                    ON CONFLICT (business_id) DO UPDATE
                    SET business_id = EXCLUDED.business_id
                    RETURNING id
                """
                content_row = await conn.fetchrow(
                    content_sql, business_id, json.dumps(source_payload)
                )
                content_id = str(content_row["id"])

                # 如果有上下文，插入或获取上下文ID
                context_id = None
                if context is not None:
                    context_sql = """
                        INSERT INTO th_contexts (context_hash, context_payload_json)
                        VALUES ($1, $2)
                        ON CONFLICT (context_hash) DO UPDATE
                        SET context_hash = EXCLUDED.context_hash
                        RETURNING id
                    """
                    context_row = await conn.fetchrow(
                        context_sql, context_hash, json.dumps(context)
                    )
                    context_id = str(context_row["id"])

                return content_id, context_id
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"确保内容和上下文失败: {e}") from e

    async def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        # 创建一个队列来存储通知
        queue: asyncio.Queue[str] = asyncio.Queue()

        def notify_handler(
            connection: Any, pid: int, channel: str, payload: str
        ) -> None:
            # 将通知放入队列
            queue.put_nowait(payload)

        try:
            async with self._transaction() as conn:
                # 监听数据库通知
                await conn.add_listener(self.NOTIFICATION_CHANNEL, notify_handler)

                # 持续从队列中获取通知并生成
                while True:
                    try:
                        notification = await asyncio.wait_for(queue.get(), timeout=1.0)
                        yield notification
                    except asyncio.TimeoutError:
                        continue
        except asyncpg.PostgresError as e:
            logger.error(f"监听通知失败: {e}")
            raise DatabaseError(f"监听通知失败: {e}") from e

    async def reset_stale_tasks(self) -> None:
        try:
            async with self._transaction() as conn:
                # 重置超过1小时仍未完成的翻译任务
                await conn.execute(
                    """
                    UPDATE th_translations
                    SET status = 'PENDING', engine = NULL, error = NULL
                    WHERE status = 'TRANSLATING'
                      AND last_updated_at < now() - interval '1 hour'
                    """
                )
                logger.info("陈旧任务已重置")
        except asyncpg.PostgresError as e:
            logger.error(f"重置陈旧任务失败: {e}")
            raise DatabaseError(f"重置陈旧任务失败: {e}") from e

    async def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        # 构建状态条件
        status_conditions = " OR ".join(
            [f"status = '{status.value}'" for status in statuses]
        )

        # 构建SQL查询
        sql = f"""
            SELECT
                t.id AS translation_id,
                c.source_payload_json,
                ctx.context_payload_json,
                t.lang_code
            FROM th_translations t
            JOIN th_content c ON t.content_id = c.id
            LEFT JOIN th_contexts ctx ON t.context_id = ctx.id
            WHERE t.lang_code = $1
              AND ({status_conditions})
        """

        # 添加限制条件
        if limit is not None:
            sql += f" LIMIT {limit}"

        try:
            offset = 0
            while True:
                # 添加偏移量
                batch_sql = sql + f" OFFSET {offset} LIMIT {batch_size}"

                async with self._transaction() as conn:
                    rows = await conn.fetch(batch_sql, lang_code)

                # 如果没有更多行，停止迭代
                if not rows:
                    break

                # 转换行为ContentItem对象
                items = []
                for row in rows:
                    # 获取content_id和context_id
                    content_sql = (
                        "SELECT business_id, source_lang FROM th_content WHERE id = $1"
                    )
                    content_row = await conn.fetchrow(content_sql, row["content_id"])

                    items.append(
                        ContentItem(
                            translation_id=str(row["translation_id"]),
                            business_id=content_row["business_id"],
                            content_id=row["content_id"],
                            context_id=row["context_id"],
                            source_payload=json.loads(row["source_payload_json"]),
                            context=json.loads(row["context_payload_json"])
                            if row["context_payload_json"]
                            else None,
                            source_lang=content_row["source_lang"],
                        )
                    )

                # 生成批次
                yield items

                # 更新偏移量
                offset += batch_size

                # 如果返回的行数少于批次大小，说明已经处理完所有行
                if len(rows) < batch_size:
                    break
        except asyncpg.PostgresError as e:
            logger.error(f"流式传输可翻译项目失败: {e}")
            raise DatabaseError(f"流式传输可翻译项目失败: {e}") from e

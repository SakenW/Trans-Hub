# trans_hub/persistence/postgres.py
"""
提供了基于 asyncpg 的 PostgreSQL 持久化实现。

本模块是 `PersistenceHandler` 协议的 PostgreSQL 具体实现，
为 Trans-Hub 提供了高性能、高并发的生产级数据后端。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:
    import asyncpg
except ImportError:
    asyncpg = None

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


class _DryRunExit(Exception):
    """一个内部异常，用于在 dry_run 模式下安全地回滚事务。"""

    pass


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
        self._pool: Optional["asyncpg.Pool"] = None
        self._notification_queue: Optional["asyncio.Queue[str]"] = None
        logger.info("PostgreSQL 持久层已配置")

    async def connect(self) -> None:
        """建立与数据库的连接池。"""
        if self._pool is None:
            try:

                def _jsonb_encoder(value: Any) -> str:
                    return json.dumps(value, ensure_ascii=False)

                def _jsonb_decoder(value: str) -> Any:
                    return json.loads(value)

                self._pool = await asyncpg.create_pool(
                    self.dsn,
                    min_size=5,
                    max_size=20,
                    init=lambda conn: conn.set_type_codec(
                        "jsonb",
                        encoder=_jsonb_encoder,
                        decoder=_jsonb_decoder,
                        schema="pg_catalog",
                    ),
                )
                logger.info("已连接到 PostgreSQL 数据库并创建连接池")
            except asyncpg.PostgresError as e:
                logger.error("连接 PostgreSQL 数据库失败", exc_info=True)
                raise DatabaseError(f"数据库连接失败: {e}") from e

    async def close(self) -> None:
        """关闭数据库连接池和所有相关连接。"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("已关闭与 PostgreSQL 数据库的连接池")

    async def reset_stale_tasks(self) -> None:
        """[实现] 在启动时重置所有处于“TRANSLATING”状态的旧任务为“PENDING”。"""
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")
        sql = """
            UPDATE th_translations
            SET status = 'PENDING', error = NULL
            WHERE status = 'TRANSLATING'
              AND last_updated_at < (now() at time zone 'utc') - interval '1 hour'
            RETURNING id;
        """
        try:
            async with self._pool.acquire() as conn:
                updated_rows = await conn.fetch(sql)
                if updated_rows:
                    logger.warning(
                        "系统自愈：重置了遗留的翻译任务", count=len(updated_rows)
                    )
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"重置陈旧任务失败: {e}") from e

    async def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        """[实现] 使用 `SELECT ... FOR UPDATE SKIP LOCKED` 从 PG 流式获取任务。"""
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")

        processed_count = 0
        status_values = tuple(s.value for s in statuses)

        while limit is None or processed_count < limit:
            current_batch_size = min(
                batch_size,
                (limit - processed_count) if limit is not None else batch_size,
            )
            if current_batch_size <= 0:
                break

            items: list[ContentItem] = []
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    locked_ids_sql = """
                        SELECT id FROM th_translations
                        WHERE lang_code = $1 AND status = ANY($2)
                        ORDER BY context_id, last_updated_at ASC
                        LIMIT $3
                        FOR UPDATE SKIP LOCKED;
                    """
                    locked_rows = await conn.fetch(
                        locked_ids_sql, lang_code, status_values, current_batch_size
                    )
                    if not locked_rows:
                        break

                    batch_ids = [row["id"] for row in locked_rows]
                    await conn.execute(
                        """
                        UPDATE th_translations
                        SET status = 'TRANSLATING',
                            last_updated_at = (now() at time zone 'utc')
                        WHERE id = ANY($1);
                        """,
                        batch_ids,
                    )

                    details_sql = """
                        SELECT
                            t.id AS translation_id,
                            c.business_id,
                            t.content_id,
                            t.context_id,
                            t.source_lang,
                            c.source_payload_json,
                            ctx.context_payload_json
                        FROM th_translations t
                        JOIN th_content c ON t.content_id = c.id
                        LEFT JOIN th_contexts ctx ON t.context_id = ctx.id
                        WHERE t.id = ANY($1)
                        ORDER BY t.context_id, t.last_updated_at ASC;
                    """
                    detail_rows = await conn.fetch(details_sql, batch_ids)
                    items = [
                        ContentItem(
                            translation_id=str(r["translation_id"]),
                            business_id=r["business_id"],
                            content_id=str(r["content_id"]),
                            context_id=str(r["context_id"])
                            if r["context_id"]
                            else None,
                            source_payload=r["source_payload_json"],
                            context=r["context_payload_json"],
                            source_lang=r["source_lang"],
                        )
                        for r in detail_rows
                    ]
            if not items:
                break
            yield items
            processed_count += len(items)

    async def ensure_content_and_context(
        self,
        business_id: str,
        source_payload: dict[str, Any],
        context: Optional[dict[str, Any]],
    ) -> tuple[str, Optional[str]]:
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")
        async with self._pool.acquire() as conn:
            try:
                content_sql = """
                    INSERT INTO th_content (business_id, source_payload_json)
                    VALUES ($1, $2)
                    ON CONFLICT (business_id) DO UPDATE
                    SET source_payload_json = EXCLUDED.source_payload_json,
                        updated_at = (now() at time zone 'utc')
                    RETURNING id;
                """
                content_row = await conn.fetchrow(
                    content_sql, business_id, source_payload
                )
                content_id = str(content_row["id"])

                context_id: Optional[str] = None
                if context:
                    context_hash = get_context_hash(context)
                    context_sql = """
                        INSERT INTO th_contexts (context_hash, context_payload_json)
                        VALUES ($1, $2)
                        ON CONFLICT (context_hash) DO NOTHING
                        RETURNING id;
                    """
                    ctx_row = await conn.fetchrow(context_sql, context_hash, context)
                    if not ctx_row:
                        ctx_row = await conn.fetchrow(
                            "SELECT id FROM th_contexts WHERE context_hash = $1",
                            context_hash,
                        )
                    context_id = str(ctx_row["id"])

                await conn.execute(
                    """
                    INSERT INTO th_jobs (content_id, last_requested_at)
                    VALUES ($1, (now() at time zone 'utc'))
                    ON CONFLICT (content_id) DO UPDATE
                    SET last_requested_at = (now() at time zone 'utc');
                    """,
                    content_id,
                )
                return content_id, context_id
            except asyncpg.PostgresError as e:
                raise DatabaseError(f"确保内容和上下文失败: {e}") from e

    async def create_pending_translations(
        self,
        content_id: str,
        context_id: Optional[str],
        target_langs: list[str],
        source_lang: Optional[str],
        engine_version: str,
        force_retranslate: bool = False,
    ) -> None:
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")
        try:
            async with self._pool.acquire() as conn:
                if force_retranslate:
                    sql = """
                        INSERT INTO th_translations AS t (
                            content_id, context_id, lang_code, source_lang,
                            engine_version
                        )
                        SELECT $1, $2, lang.code, $3, $4
                        FROM unnest($5::text[]) AS lang(code)
                        ON CONFLICT (content_id, context_id, lang_code) DO UPDATE
                        SET status = 'PENDING',
                            source_lang = EXCLUDED.source_lang,
                            engine_version = EXCLUDED.engine_version,
                            translation_payload_json = NULL,
                            error = NULL,
                            last_updated_at = (now() at time zone 'utc');
                    """
                else:
                    sql = """
                        INSERT INTO th_translations (
                            content_id, context_id, lang_code, source_lang,
                            engine_version
                        )
                        SELECT $1, $2, lang.code, $3, $4
                        FROM unnest($5::text[]) AS lang(code)
                        ON CONFLICT (content_id, context_id, lang_code) DO NOTHING;
                    """
                await conn.execute(
                    sql,
                    content_id,
                    context_id,
                    source_lang,
                    engine_version,
                    target_langs,
                )
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"创建待处理翻译失败: {e}") from e

    async def save_translation_results(self, results: list[TranslationResult]) -> None:
        if not results or not self._pool:
            return
        params = [
            (
                res.status.value,
                res.translated_payload,
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
                translation_payload_json = $2,
                engine = $3,
                error = $4,
                last_updated_at = (now() at time zone 'utc')
            WHERE id = $5::uuid AND status = 'TRANSLATING';
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.executemany(sql, params)
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"保存翻译结果失败: {e}") from e

    async def find_translation(
        self,
        business_id: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")
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
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(sql, business_id, target_lang, context_hash)
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"查找翻译失败: {e}") from e
        if not row:
            return None
        return TranslationResult(
            translation_id=str(row["translation_id"]),
            business_id=business_id,
            original_payload=row["source_payload_json"],
            translated_payload=row["translation_payload_json"],
            target_lang=target_lang,
            status=TranslationStatus(row["status"]),
            engine=row["engine"],
            from_cache=True,
            error=row["error"],
            context_hash=context_hash,
        )

    async def garbage_collect(
        self,
        retention_days: int,
        dry_run: bool = False,
        _now: Optional[datetime] = None,
    ) -> dict[str, int]:
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")

        now = _now or datetime.now(timezone.utc)
        cutoff_date = (now - timedelta(days=retention_days)).date()

        stats = {"deleted_jobs": 0, "deleted_content": 0, "deleted_contexts": 0}
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    del_jobs_sql = """
                        DELETE FROM th_jobs
                        WHERE DATE(last_requested_at) < $1
                        RETURNING id;
                    """
                    if dry_run:
                        del_jobs_sql = """
                            SELECT id FROM th_jobs
                            WHERE DATE(last_requested_at) < $1;
                        """
                    stats["deleted_jobs"] = len(
                        await conn.fetch(del_jobs_sql, cutoff_date)
                    )

                    del_content_sql = """
                        DELETE FROM th_content c
                        WHERE NOT EXISTS (
                            SELECT 1 FROM th_jobs j WHERE j.content_id = c.id
                        ) AND NOT EXISTS (
                            SELECT 1 FROM th_translations t WHERE t.content_id = c.id
                        )
                        RETURNING id;
                    """
                    if dry_run:
                        del_content_sql = """
                            SELECT id FROM th_content c
                            WHERE NOT EXISTS (
                                SELECT 1 FROM th_jobs j WHERE j.content_id = c.id
                            ) AND NOT EXISTS (
                                SELECT 1 FROM th_translations t
                                WHERE t.content_id = c.id
                            );
                        """
                    stats["deleted_content"] = len(await conn.fetch(del_content_sql))

                    del_contexts_sql = """
                        DELETE FROM th_contexts ctx
                        WHERE NOT EXISTS (
                            SELECT 1 FROM th_translations t
                            WHERE t.context_id = ctx.id
                        )
                        RETURNING id;
                    """
                    if dry_run:
                        del_contexts_sql = """
                            SELECT id FROM th_contexts ctx
                            WHERE NOT EXISTS (
                                SELECT 1 FROM th_translations t
                                WHERE t.context_id = ctx.id
                            );
                        """
                    stats["deleted_contexts"] = len(await conn.fetch(del_contexts_sql))

                    if dry_run:
                        raise _DryRunExit()
            return stats
        except _DryRunExit:
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
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        INSERT INTO th_dead_letter_queue (
                            translation_id, original_payload_json,
                            context_payload_json, target_lang_code,
                            last_error_message, engine_name, engine_version
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        item.translation_id,
                        item.source_payload,
                        item.context,
                        target_lang,
                        error_message,
                        engine_name,
                        engine_version,
                    )
                    await conn.execute(
                        "DELETE FROM th_translations WHERE id = $1", item.translation_id
                    )
                logger.info(
                    "任务已成功移至死信队列", translation_id=item.translation_id
                )
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"移动到死信队列失败: {e}") from e

    async def _notification_callback(
        self, connection: "asyncpg.Connection", pid: int, channel: str, payload: str
    ) -> None:
        if self._notification_queue:
            # 使用 try-except 避免在队列已满或关闭时抛出异常
            try:
                self._notification_queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("通知队列已满，一个通知被丢弃。")

    async def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[实现] 使用 `LISTEN/NOTIFY` 监听数据库通知。"""
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")

        listener_conn = None
        try:
            listener_conn = await self._pool.acquire()
            self._notification_queue = asyncio.Queue(maxsize=100)
            await listener_conn.add_listener(
                self.NOTIFICATION_CHANNEL, self._notification_callback
            )
            logger.info(
                "PostgreSQL 通知监听器已启动", channel=self.NOTIFICATION_CHANNEL
            )

            assert self._notification_queue is not None
            while True:
                payload = await self._notification_queue.get()
                yield payload
        except asyncio.CancelledError:
            logger.info("通知监听器被取消。")
        finally:
            # 修复：确保在生成器退出时清理所有相关资源
            self._notification_queue = None
            if listener_conn:
                try:
                    await listener_conn.remove_listener(
                        self.NOTIFICATION_CHANNEL, self._notification_callback
                    )
                except Exception as e:
                    logger.warning("移除监听器时出错", error=str(e))
                finally:
                    await self._pool.release(listener_conn)
                    logger.info("PostgreSQL 通知监听器资源已释放。")

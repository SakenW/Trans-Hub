# trans_hub/persistence/postgres.py

import asyncio
import json
import re
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Any

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


class _DryRunError(Exception):
    pass


class PostgresPersistenceHandler(PersistenceHandler):

    SUPPORTS_NOTIFICATIONS = True
    NOTIFICATION_CHANNEL = "new_translation_task"

    def __init__(self, dsn: str):
        if asyncpg is None:
            raise ImportError(
                "要使用 PostgresPersistenceHandler, 请安装 'asyncpg' 驱动。"
            )
        self.dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._notification_listener_conn: asyncpg.Connection | None = None
        self._notification_queue: asyncio.Queue[str] | None = None
        logger.info("PostgreSQL 持久层已配置")

    async def connect(self) -> None:
        if self._pool is None:
            try:
                connect_dsn = self.dsn
                if connect_dsn.startswith("postgresql+asyncpg"):
                    connect_dsn = connect_dsn.replace("postgresql+asyncpg", "postgresql", 1)

                # [修正] 코덱 설정은 JSON 데이터를 자동으로 파싱하고 덤프하는 역할을 합니다.
                # asyncpg가 JSON/JSONB를 자동으로 처리하도록 설정합니다.
                def _jsonb_encoder(value: Any) -> str:
                    return json.dumps(value, ensure_ascii=False)

                def _jsonb_decoder(value: str) -> Any:
                    return json.loads(value)
                
                assert asyncpg is not None
                self._pool = await asyncpg.create_pool(
                    dsn=connect_dsn,
                    min_size=5,
                    max_size=20,
                    init=lambda conn: conn.set_type_codec(
                        "jsonb",
                        encoder=_jsonb_encoder,
                        decoder=_jsonb_decoder,
                        schema="pg_catalog",
                        format='text' # 명시적으로 텍스트 포맷을 사용하도록 지정
                    ),
                )
                logger.info("已连接到 PostgreSQL 数据库并创建连接池")
            except asyncpg.PostgresError as e:
                logger.error("连接 PostgreSQL 数据库失败", exc_info=True)
                raise DatabaseError(f"数据库连接失败: {e}") from e

    # ... (close, reset_stale_tasks 保持不变) ...
    async def close(self) -> None:
        if (
            self._notification_listener_conn
            and not self._notification_listener_conn.is_closed()
        ):
            if self._pool:
                try:
                    assert asyncpg is not None
                    await self._notification_listener_conn.remove_listener(
                        self.NOTIFICATION_CHANNEL, self._notification_callback
                    )
                except asyncpg.InterfaceError:
                    pass
            await self._notification_listener_conn.close()
            self._notification_listener_conn = None
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("已关闭与 PostgreSQL 数据库的连接池")

    async def reset_stale_tasks(self) -> None:
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")
        sql = """
            UPDATE th_translations SET status = 'PENDING', error = NULL
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
        limit: int | None = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
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
                        LIMIT $3 FOR UPDATE SKIP LOCKED;
                    """
                    locked_rows = await conn.fetch(
                        locked_ids_sql, lang_code, status_values, current_batch_size
                    )
                    if not locked_rows:
                        break
                    batch_ids = [row["id"] for row in locked_rows]
                    await conn.execute(
                        "UPDATE th_translations SET status = 'TRANSLATING', last_updated_at = (now() at time zone 'utc') WHERE id = ANY($1);",
                        batch_ids,
                    )
                    details_sql = """
                        SELECT t.id AS translation_id, c.business_id, t.content_id, t.context_id, t.source_lang,
                               c.source_payload_json, ctx.context_payload_json
                        FROM th_translations t
                        JOIN th_content c ON t.content_id = c.id
                        LEFT JOIN th_contexts ctx ON t.context_id = ctx.id
                        WHERE t.id = ANY($1) ORDER BY t.context_id, t.last_updated_at ASC;
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
                            # [核心修复] 手动反序列化, 因为 asyncpg 的 codec 可能不总是生效
                            source_payload=json.loads(r["source_payload_json"]) if isinstance(r["source_payload_json"], str) else r["source_payload_json"],
                            context=json.loads(r["context_payload_json"]) if r["context_payload_json"] and isinstance(r["context_payload_json"], str) else r["context_payload_json"],
                            source_lang=r["source_lang"],
                        )
                        for r in detail_rows
                    ]
            if not items:
                break
            yield items
            processed_count += len(items)

    # ... (ensure_content_and_context, create_pending_translations 保持不变) ...
    async def ensure_content_and_context(
        self,
        business_id: str,
        source_payload: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> tuple[str, str | None]:
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")
        async with self._pool.acquire() as conn:
            try:
                existing_id_row = await conn.fetchrow(
                    "SELECT id FROM th_content WHERE business_id = $1", business_id
                )
                
                content_id = str(existing_id_row['id']) if existing_id_row else str(uuid.uuid4())
                
                content_sql = """
                    INSERT INTO th_content (id, business_id, source_payload_json) VALUES ($1, $2, $3)
                    ON CONFLICT (business_id) DO UPDATE SET
                        source_payload_json = EXCLUDED.source_payload_json,
                        updated_at = (now() at time zone 'utc')
                    RETURNING id;
                """
                source_payload_str = json.dumps(source_payload, ensure_ascii=False)
                content_row = await conn.fetchrow(
                    content_sql, content_id, business_id, source_payload_str
                )
                assert content_row
                content_id = str(content_row["id"])

                context_id: str | None = None
                if context:
                    context_hash = get_context_hash(context)
                    
                    existing_ctx_id_row = await conn.fetchrow(
                        "SELECT id FROM th_contexts WHERE context_hash = $1", context_hash
                    )
                    
                    ctx_id = str(existing_ctx_id_row['id']) if existing_ctx_id_row else str(uuid.uuid4())
                    
                    context_sql = """
                        INSERT INTO th_contexts (id, context_hash, context_payload_json) VALUES ($1, $2, $3)
                        ON CONFLICT (context_hash) DO NOTHING RETURNING id;
                    """
                    context_str = json.dumps(context, ensure_ascii=False)
                    ctx_row = await conn.fetchrow(context_sql, ctx_id, context_hash, context_str)
                    
                    if not ctx_row:
                        ctx_row = await conn.fetchrow(
                            "SELECT id FROM th_contexts WHERE context_hash = $1",
                            context_hash,
                        )
                    assert ctx_row
                    context_id = str(ctx_row["id"])

                job_id = str(uuid.uuid4())
                await conn.execute(
                    """
                    INSERT INTO th_jobs (id, content_id, last_requested_at) VALUES ($1, $2, (now() at time zone 'utc'))
                    ON CONFLICT (content_id) DO UPDATE SET last_requested_at = (now() at time zone 'utc');
                    """,
                    job_id, content_id
                )
                return content_id, context_id
            except asyncpg.PostgresError as e:
                raise DatabaseError(f"确保内容和上下文失败: {e}") from e

    async def create_pending_translations(
        self,
        content_id: str,
        context_id: str | None,
        target_langs: list[str],
        source_lang: str | None,
        engine_version: str,
        force_retranslate: bool = False,
    ) -> None:
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")
        try:
            async with self._pool.acquire() as conn:
                if force_retranslate:
                    update_sql = """
                        UPDATE th_translations SET
                            status = 'PENDING', source_lang = $4,
                            engine_version = $5, translation_payload_json = NULL,
                            error = NULL, last_updated_at = (now() at time zone 'utc')
                        WHERE content_id = $1 
                          AND COALESCE(context_id::text, 'NULL') = COALESCE($2::text, 'NULL')
                          AND lang_code = ANY($3::text[]);
                    """
                    await conn.execute(update_sql, content_id, context_id, target_langs, source_lang, engine_version)

                insert_sql = """
                    INSERT INTO th_translations (id, content_id, context_id, lang_code, source_lang, engine_version, status)
                    SELECT gen_random_uuid(), $1, $2, lang.code, $3, $4, 'PENDING'
                    FROM unnest($5::text[]) AS lang(code)
                    ON CONFLICT (content_id, context_id, lang_code) DO NOTHING;
                """
                await conn.execute(
                    insert_sql,
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
                json.dumps(res.translated_payload, ensure_ascii=False) if res.translated_payload else None,
                res.engine,
                res.error,
                res.translation_id,
            )
            for res in results
        ]
        sql = """
            UPDATE th_translations SET status = $1, translation_payload_json = $2,
                engine = $3, error = $4, last_updated_at = (now() at time zone 'utc')
            WHERE id = $5::uuid AND status = 'TRANSLATING';
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.executemany(sql, params)
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"保存翻译结果失败: {e}") from e
    
    async def find_translation(
        self, business_id: str, target_lang: str, context: dict[str, Any] | None = None
    ) -> TranslationResult | None:
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")
        context_hash = get_context_hash(context)
        sql = """
            SELECT t.id AS translation_id, c.source_payload_json, t.translation_payload_json,
                   t.status, t.engine, t.error
            FROM th_translations t JOIN th_content c ON t.content_id = c.id
            LEFT JOIN th_contexts ctx ON t.context_id = ctx.id
            WHERE c.business_id = $1 AND t.lang_code = $2 AND COALESCE(ctx.context_hash, '__GLOBAL__') = $3
            ORDER BY t.last_updated_at DESC LIMIT 1;
        """
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(sql, business_id, target_lang, context_hash)
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"查找翻译失败: {e}") from e
        if not row:
            return None
        # [修正] 从数据库读取时也需要反序列化
        original_payload = json.loads(row["source_payload_json"]) if isinstance(row["source_payload_json"], str) else row["source_payload_json"]
        translated_payload = json.loads(row["translation_payload_json"]) if row["translation_payload_json"] and isinstance(row["translation_payload_json"], str) else row["translation_payload_json"]
        
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
        self, retention_days: int, dry_run: bool = False, _now: datetime | None = None
    ) -> dict[str, int]:
        if not self._pool:
            raise DatabaseError("数据库连接池未初始化")
        stats = {"deleted_jobs": 0, "deleted_content": 0, "deleted_contexts": 0}
        now = _now if _now is not None else datetime.now(timezone.utc)
        cutoff_date = now.date() - timedelta(days=retention_days)

        # [核心修复] _parse_delete_status 接受 str
        def _parse_delete_status(status: str) -> int:
            match = re.search(r"DELETE\s(\d+)", status)
            return int(match.group(1)) if match else 0

        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    job_where_clause = "WHERE (last_requested_at::date) < $1"
                    if dry_run:
                        res = await conn.fetchval(
                            f"SELECT COUNT(*) FROM th_jobs {job_where_clause}",
                            cutoff_date,
                        )
                        stats["deleted_jobs"] = res if res else 0
                    else:
                        status = await conn.execute(
                            f"DELETE FROM th_jobs {job_where_clause}", cutoff_date
                        )
                        stats["deleted_jobs"] = _parse_delete_status(status)

                    orphan_content_sql = """ FROM th_content c WHERE NOT EXISTS (SELECT 1 FROM th_jobs j WHERE j.content_id = c.id)
                                             AND NOT EXISTS (SELECT 1 FROM th_translations t WHERE t.content_id = c.id)"""
                    if dry_run:
                        res = await conn.fetchval(
                            f"SELECT COUNT(*) {orphan_content_sql}"
                        )
                        stats["deleted_content"] = res if res else 0
                    else:
                        status = await conn.execute(f"DELETE FROM th_content WHERE id IN (SELECT id {orphan_content_sql})")
                        stats["deleted_content"] = _parse_delete_status(status)

                    orphan_context_sql = """ FROM th_contexts ctx WHERE NOT EXISTS (SELECT 1 FROM th_translations t WHERE t.context_id = ctx.id)"""
                    if dry_run:
                        res = await conn.fetchval(
                            f"SELECT COUNT(*) {orphan_context_sql}"
                        )
                        stats["deleted_contexts"] = res if res else 0
                    else:
                        status = await conn.execute(f"DELETE FROM th_contexts WHERE id IN (SELECT id {orphan_context_sql})")
                        stats["deleted_contexts"] = _parse_delete_status(status)

                    if dry_run:
                        raise _DryRunError()
            return stats
        except _DryRunError:
            logger.info("垃圾回收 (dry run) 完成，事务已回滚。")
            return stats
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"垃圾回收失败: {e}") from e
    # ... (rest of the file remains the same) ...
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
                        INSERT INTO th_dead_letter_queue (translation_id, original_payload_json,
                            context_payload_json, target_lang_code, last_error_message, engine_name, engine_version)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        item.translation_id,
                        json.dumps(item.source_payload, ensure_ascii=False),
                        json.dumps(item.context, ensure_ascii=False) if item.context else None,
                        target_lang,
                        error_message,
                        engine_name,
                        engine_version,
                    )
                    await conn.execute(
                        "DELETE FROM th_translations WHERE id = $1::uuid",
                        item.translation_id,
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
            await self._notification_queue.put(payload)

    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        async def _internal_generator() -> AsyncGenerator[str, None]:
            if not self._pool:
                raise DatabaseError("数据库连接池未初始化")
            try:
                if (
                    not self._notification_listener_conn
                    or self._notification_listener_conn.is_closed()
                ):
                    assert asyncpg is not None
                    self._notification_listener_conn = await self._pool.acquire()
                    self._notification_queue = asyncio.Queue()
                    await self._notification_listener_conn.add_listener(
                        self.NOTIFICATION_CHANNEL, self._notification_callback
                    )
                    logger.info(
                        "PostgreSQL 通知监听器已启动", channel=self.NOTIFICATION_CHANNEL
                    )
                assert self._notification_queue is not None
                while True:
                    payload = await self._notification_queue.get()
                    yield payload
            finally:
                logger.warning("PostgreSQL 通知监听器正在关闭和清理资源...")
                if (
                    self._pool
                    and self._notification_listener_conn
                    and not self._notification_listener_conn.is_closed()
                ):
                    assert asyncpg is not None
                    await self._notification_listener_conn.remove_listener(
                        self.NOTIFICATION_CHANNEL, self._notification_callback
                    )
                    await self._pool.release(self._notification_listener_conn)
                self._notification_listener_conn = None
                self._notification_queue = None
                logger.info("PostgreSQL 通知监听器资源已成功清理。")

        return _internal_generator()
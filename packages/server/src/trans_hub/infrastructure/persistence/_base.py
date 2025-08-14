# packages/server/src/trans_hub/infrastructure/persistence/_base.py
"""
持久化处理器的基类，封装了使用 SQLAlchemy ORM 实现的、
跨数据库方言共享的核心数据访问逻辑。(v2.5.14 对齐版)
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trans_hub.infrastructure.db._schema import (
    ThComments,
    ThContent,
    ThEvents,
    ThLocalesFallbacks,
    ThProjects,
    ThTmLinks,
    ThTmUnits,
    ThTransHead,
    ThTransRev,
)
from trans_hub_core.exceptions import DatabaseError
from trans_hub_core.interfaces import PersistenceHandler
from trans_hub_core.types import (
    Comment,
    ContentItem,
    Event,
    TranslationHead,
    TranslationStatus,
)
from trans_hub_uida import generate_uida

logger = structlog.get_logger(__name__)


class BasePersistenceHandler(PersistenceHandler, ABC):
    """持久化处理器的共享基类。"""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        self._sessionmaker = sessionmaker

    @abstractmethod
    async def connect(self) -> None:
        """[子类实现] 确保与数据库的连接是活跃的，并执行方言特定的初始化。"""
        pass

    async def close(self) -> None:
        """关闭所有与数据库的连接。"""
        engine = self._sessionmaker.kw.get("bind")
        if engine:
            await engine.dispose()
        logger.info("持久化层引擎已关闭。")

    @abstractmethod
    def _get_upsert_stmt(
        self,
        model: Any,
        values: dict[str, Any],
        index_elements: list[str],
        update_cols: list[str],
    ) -> Any:
        """[子类实现] 返回方言特定的原子化 upsert 语句。"""
        raise NotImplementedError

    async def upsert_content(
        self,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        source_payload: dict[str, Any],
        source_lang: str,
        content_version: int,  # 保留接口签名，但ORM模型中已无此字段
    ) -> str:
        """根据 UIDA 幂等地创建或更新一条内容记录。"""
        uida_components = generate_uida(keys)
        try:
            async with self._sessionmaker.begin() as session:
                # 1. 确保项目存在
                project_values = {"project_id": project_id, "display_name": project_id}
                project_stmt = self._get_upsert_stmt(
                    ThProjects,
                    project_values,
                    index_elements=["project_id"],
                    update_cols=["display_name"],
                )
                await session.execute(project_stmt)

                # 2. 查找现有内容记录
                select_stmt = select(ThContent.id).where(
                    ThContent.project_id == project_id,
                    ThContent.namespace == namespace,
                    ThContent.keys_sha256_bytes == uida_components.keys_sha256_bytes,
                )
                existing_id = (await session.execute(select_stmt)).scalar_one_or_none()

                if existing_id:
                    # 3a. 如果存在，则更新
                    update_stmt = (
                        update(ThContent)
                        .where(ThContent.id == existing_id)
                        .values(
                            source_payload_json=source_payload, updated_at=func.now()
                        )
                    )
                    await session.execute(update_stmt)
                    return existing_id
                else:
                    # 3b. 如果不存在，则创建
                    new_content = ThContent(
                        id=str(uuid.uuid4()),
                        project_id=project_id,
                        namespace=namespace,
                        keys_sha256_bytes=uida_components.keys_sha256_bytes,
                        source_lang=source_lang,
                        source_payload_json=source_payload,
                    )
                    session.add(new_content)
                    await session.flush()  # 刷新以在事务内获取 ID
                    return new_content.id
        except SQLAlchemyError as e:
            logger.error("Upsert content 失败", exc_info=True)
            raise DatabaseError(f"Upsert content 失败: {e}") from e

    async def get_content_id_by_uida(
        self, project_id: str, namespace: str, keys_sha256_bytes: bytes
    ) -> str | None:
        """根据 UIDA 的核心部分查找内容ID。"""
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThContent.id).where(
                    ThContent.project_id == project_id,
                    ThContent.namespace == namespace,
                    ThContent.keys_sha256_bytes == keys_sha256_bytes,
                )
                return (await session.execute(stmt)).scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseError(f"通过 UIDA 获取 content_id 失败: {e}") from e

    async def get_or_create_translation_head(
        self,
        project_id: str,
        content_id: str,
        target_lang: str,
        variant_key: str,
    ) -> tuple[str, int]:
        """获取或创建一个翻译头记录，返回 (head_id, current_revision_no)。"""
        try:
            async with self._sessionmaker.begin() as session:
                stmt = select(ThTransHead).where(
                    ThTransHead.project_id == project_id,
                    ThTransHead.content_id == content_id,
                    ThTransHead.target_lang == target_lang,
                    ThTransHead.variant_key == variant_key,
                )
                head = (await session.execute(stmt)).scalar_one_or_none()
                if head:
                    return head.id, head.current_no

                content = await session.get(ThContent, content_id)
                if not content:
                    raise ValueError(
                        f"尝试为不存在的内容创建翻译头: content_id={content_id}"
                    )

                initial_rev = ThTransRev(
                    project_id=project_id,
                    content_id=content_id,
                    target_lang=target_lang,
                    variant_key=variant_key,
                    status=TranslationStatus.DRAFT,
                    revision_no=0,
                    src_payload_json=content.source_payload_json,
                    translated_payload_json=None,
                )
                session.add(initial_rev)
                await session.flush()

                new_head = ThTransHead(
                    project_id=project_id,
                    content_id=content_id,
                    target_lang=target_lang,
                    variant_key=variant_key,
                    current_rev_id=initial_rev.id,
                    current_status=initial_rev.status,
                    current_no=0,
                )
                session.add(new_head)
                await session.flush()
                return new_head.id, 0
        except SQLAlchemyError as e:
            raise DatabaseError(f"获取或创建翻译头记录失败: {e}") from e

    async def create_new_translation_revision(
        self, *, head_id: str, project_id: str, content_id: str, **kwargs: Any
    ) -> str:
        """在 th_trans_rev 中创建一条新的修订，并更新 th_trans_head 的指针。"""
        try:
            async with self._sessionmaker.begin() as session:
                head = (
                    await session.execute(
                        select(ThTransHead).where(
                            ThTransHead.project_id == project_id,
                            ThTransHead.id == head_id,
                        )
                    )
                ).scalar_one()

                content = await session.get(ThContent, content_id)
                if not content:
                    raise ValueError(f"内容记录未找到: content_id={content_id}")

                new_rev = ThTransRev(
                    project_id=project_id,
                    content_id=content_id,
                    src_payload_json=content.source_payload_json,
                    **kwargs,
                )
                session.add(new_rev)
                await session.flush()

                head.current_rev_id = new_rev.id
                head.current_status = new_rev.status
                head.current_no = new_rev.revision_no

                return new_rev.id
        except NoResultFound:
            raise ValueError(f"翻译头记录未找到: head_id={head_id}") from None
        except SQLAlchemyError as e:
            raise DatabaseError(f"创建新翻译修订失败: {e}") from e

    async def find_tm_entry(
        self, *, project_id: str, namespace: str, reuse_sha: bytes, **kwargs: Any
    ) -> tuple[str, dict[str, Any]] | None:
        """在 TM 中查找可复用的翻译。"""
        try:
            # 动态过滤项的允许列表：将传入的 key 映射到 ORM 列
            ALLOWED_FILTERS = {
                "src_lang": ThTmUnits.src_lang,
                "tgt_lang": ThTmUnits.tgt_lang,
                "variant_key": ThTmUnits.variant_key,
            }

            conditions = [
                ThTmUnits.project_id == project_id,
                ThTmUnits.namespace == namespace,
                ThTmUnits.src_hash == reuse_sha,
                ThTmUnits.approved.is_(True),
            ]

            for k, v in kwargs.items():
                if v is None:
                    continue
                col = ALLOWED_FILTERS.get(k)
                if col is not None:
                    conditions.append(col == v)

            async with self._sessionmaker() as session:
                stmt = (
                    select(ThTmUnits.id, ThTmUnits.tgt_payload)
                    .where(*conditions)
                    .order_by(ThTmUnits.updated_at.desc())
                    .limit(1)
                )
                res = await session.execute(stmt)
                row = res.first()
                if not row:
                    return None
                tm_id, tgt_payload = row
                return str(tm_id), (tgt_payload or {})
        except SQLAlchemyError as e:
            raise DatabaseError(f"查找 TM 条目失败: {e}") from e

    async def upsert_tm_entry(self, *, project_id: str, **kwargs: Any) -> str:
        """幂等地创建或更新 TM 条目。"""
        try:
            async with self._sessionmaker.begin() as session:
                values = {
                    "project_id": project_id,
                    "updated_at": func.now(),
                    **kwargs,
                }
                if "id" not in values:
                    values["id"] = str(uuid.uuid4())

                stmt = self._get_upsert_stmt(
                    ThTmUnits,
                    values,
                    index_elements=[
                        "project_id",
                        "namespace",
                        "src_hash",
                        "tgt_lang",
                        "variant_key",
                    ],
                    update_cols=["tgt_payload", "approved", "updated_at"],
                ).returning(ThTmUnits.id)
                return (await session.execute(stmt)).scalar_one()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Upsert TM entry 失败: {e}") from e

    async def link_translation_to_tm(
        self, translation_rev_id: str, tm_id: str, project_id: str
    ) -> None:
        """在 th_tm_links 中创建一条追溯链接。"""
        try:
            async with self._sessionmaker.begin() as session:
                values = {
                    "id": str(uuid.uuid4()),
                    "project_id": project_id,
                    "translation_rev_id": translation_rev_id,
                    "tm_id": tm_id,
                }
                stmt = self._get_upsert_stmt(
                    ThTmLinks,
                    values,
                    index_elements=["project_id", "translation_rev_id", "tm_id"],
                    update_cols=[],
                )
                await session.execute(stmt)
        except SQLAlchemyError as e:
            raise DatabaseError(f"链接 TM 失败: {e}") from e

    async def get_published_translation(
        self, content_id: str, target_lang: str, variant_key: str
    ) -> tuple[str, dict[str, Any]] | None:
        """获取已发布的译文。"""
        try:
            async with self._sessionmaker() as session:
                stmt = (
                    select(
                        ThTransHead.published_rev_id,
                        ThTransRev.translated_payload_json,
                    )
                    .join(
                        ThTransRev,
                        (ThTransHead.project_id == ThTransRev.project_id)
                        & (ThTransHead.published_rev_id == ThTransRev.id),
                    )
                    .where(
                        ThTransHead.content_id == content_id,
                        ThTransHead.target_lang == target_lang,
                        ThTransHead.variant_key == variant_key,
                        ThTransHead.published_rev_id.is_not(None),
                    )
                )
                result = (await session.execute(stmt)).first()
                if result:
                    return result.published_rev_id, result.translated_payload_json
                return None
        except SQLAlchemyError as e:
            raise DatabaseError(f"获取已发布翻译失败: {e}") from e

    async def publish_revision(self, revision_id: str) -> bool:
        """将一个 'reviewed' 状态的修订发布。"""
        try:
            async with self._sessionmaker.begin() as session:
                rev_stmt = select(ThTransRev).where(ThTransRev.id == revision_id)
                rev = (await session.execute(rev_stmt)).scalar_one_or_none()

                if not rev or rev.status != TranslationStatus.REVIEWED.value:
                    logger.warning(
                        "发布失败: 修订不存在或状态不是 'reviewed'",
                        rev_id=revision_id,
                        status=getattr(rev, "status", None),
                    )
                    return False

                rev.status = TranslationStatus.PUBLISHED.value

                head_stmt = select(ThTransHead).where(
                    ThTransHead.project_id == rev.project_id,
                    ThTransHead.content_id == rev.content_id,
                    ThTransHead.target_lang == rev.target_lang,
                    ThTransHead.variant_key == rev.variant_key,
                )
                head = (await session.execute(head_stmt)).scalar_one()

                head.published_rev_id = rev.id
                head.published_no = rev.revision_no
                head.published_at = datetime.now(timezone.utc)
                # 发布时，current 指针也应同步到最新发布版
                head.current_rev_id = rev.id
                head.current_status = TranslationStatus.PUBLISHED.value
                head.current_no = rev.revision_no

                return True
        except NoResultFound:
            logger.warning("发布失败: 未找到对应的 Head 记录", rev_id=revision_id)
            return False
        except SQLAlchemyError as e:
            raise DatabaseError(f"发布修订失败: {e}") from e

    async def reject_revision(self, revision_id: str) -> bool:
        """将一个修订的状态标记为 'rejected'。"""
        try:
            async with self._sessionmaker.begin() as session:
                rev_stmt = select(ThTransRev).where(ThTransRev.id == revision_id)
                rev = (await session.execute(rev_stmt)).scalar_one_or_none()

                if not rev:
                    logger.warning("拒绝失败: 修订不存在", rev_id=revision_id)
                    return False

                rev.status = TranslationStatus.REJECTED.value

                update_head_stmt = (
                    update(ThTransHead)
                    .where(ThTransHead.current_rev_id == revision_id)
                    .values(current_status=TranslationStatus.REJECTED.value)
                    .execution_options(synchronize_session=False)
                )
                await session.execute(update_head_stmt)

                return True
        except SQLAlchemyError as e:
            raise DatabaseError(f"拒绝修订失败: {e}") from e

    async def write_event(self, event: Event) -> None:
        """向 th_events 写入一条事件记录。"""
        try:
            async with self._sessionmaker.begin() as session:
                db_event = ThEvents(
                    project_id=event.project_id,
                    head_id=event.head_id,
                    actor=event.actor,
                    event_type=event.event_type,
                    payload=event.payload,
                )
                session.add(db_event)
        except SQLAlchemyError as e:
            raise DatabaseError(f"写入事件失败: {e}") from e

    async def add_comment(self, comment: Comment) -> str:
        """向 th_comments 添加一条评论，返回评论 ID。"""
        try:
            async with self._sessionmaker.begin() as session:
                db_comment = ThComments(
                    project_id=comment.project_id,
                    head_id=comment.head_id,
                    author=comment.author,
                    body=comment.body,
                )
                session.add(db_comment)
                await session.flush()
                return str(db_comment.id)
        except SQLAlchemyError as e:
            raise DatabaseError(f"添加评论失败: {e}") from e

    async def get_comments(self, head_id: str) -> list[Comment]:
        """获取指定 head_id 的所有评论。"""
        try:
            async with self._sessionmaker() as session:
                stmt = (
                    select(ThComments)
                    .where(ThComments.head_id == head_id)
                    .order_by(ThComments.created_at)
                )
                results = (await session.execute(stmt)).scalars().all()
                return [
                    Comment.model_validate(r, from_attributes=True) for r in results
                ]
        except SQLAlchemyError as e:
            raise DatabaseError(f"获取评论失败: {e}") from e

    async def get_fallback_order(
        self, project_id: str, locale: str
    ) -> list[str] | None:
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThLocalesFallbacks.fallback_order).where(
                    ThLocalesFallbacks.project_id == project_id,
                    ThLocalesFallbacks.locale == locale,
                )
                return (await session.execute(stmt)).scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseError(f"获取回退顺序失败: {e}") from e

    async def set_fallback_order(
        self, project_id: str, locale: str, fallback_order: list[str]
    ) -> None:
        try:
            async with self._sessionmaker.begin() as session:
                values = {
                    "project_id": project_id,
                    "locale": locale,
                    "fallback_order": fallback_order,
                }
                stmt = self._get_upsert_stmt(
                    ThLocalesFallbacks,
                    values,
                    index_elements=["project_id", "locale"],
                    update_cols=["fallback_order"],
                )
                await session.execute(stmt)
        except SQLAlchemyError as e:
            raise DatabaseError(f"设置回退顺序失败: {e}") from e

    async def get_translation_head_by_uida(
        self,
        *,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        target_lang: str,
        variant_key: str,
    ) -> TranslationHead | None:
        """根据 UIDA 获取一个翻译头记录的 DTO。"""
        uida = generate_uida(keys)
        try:
            async with self._sessionmaker() as session:
                stmt = (
                    select(ThTransHead)
                    .join(ThContent, ThTransHead.content_id == ThContent.id)
                    .where(
                        ThTransHead.project_id == project_id,
                        ThContent.namespace == namespace,
                        ThContent.keys_sha256_bytes == uida.keys_sha256_bytes,
                        ThTransHead.target_lang == target_lang,
                        ThTransHead.variant_key == variant_key,
                    )
                )
                result = (await session.execute(stmt)).scalar_one_or_none()
                return (
                    TranslationHead.model_validate(result, from_attributes=True)
                    if result
                    else None
                )
        except SQLAlchemyError as e:
            raise DatabaseError(f"通过 UIDA 获取 Head 失败: {e}") from e

    async def get_head_by_id(self, head_id: str) -> TranslationHead | None:
        """根据 Head ID 获取一个翻译头记录的 DTO。"""
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThTransHead).where(ThTransHead.id == head_id)
                result = (await session.execute(stmt)).scalar_one_or_none()
                return (
                    TranslationHead.model_validate(result, from_attributes=True)
                    if result
                    else None
                )
        except SQLAlchemyError as e:
            raise DatabaseError(f"通过 ID 获取 Head 失败: {e}") from e

    async def get_head_by_revision(self, revision_id: str) -> TranslationHead | None:
        """根据 revision_id 查找其所属的 head 的 DTO。"""
        try:
            async with self._sessionmaker() as session:
                stmt = (
                    select(ThTransHead)
                    .where(
                        (ThTransHead.current_rev_id == revision_id)
                        | (ThTransHead.published_rev_id == revision_id)
                    )
                    .limit(1)
                )
                result = (await session.execute(stmt)).scalar_one_or_none()
                return (
                    TranslationHead.model_validate(result, from_attributes=True)
                    if result
                    else None
                )
        except SQLAlchemyError as e:
            raise DatabaseError(f"通过 Revision 获取 Head 失败: {e}") from e

    async def _build_content_items_from_orm(
        self, session: AsyncSession, head_results: list[ThTransHead]
    ) -> list[ContentItem]:
        """根据一批 Head ORM 对象，高效地构建出 ContentItem DTO 列表。"""
        if not head_results:
            return []

        content_ids = {h.content_id for h in head_results}
        content_map = {
            c.id: c
            for c in (
                await session.execute(
                    select(ThContent).where(ThContent.id.in_(content_ids))
                )
            ).scalars()
        }

        items = []
        for head in head_results:
            content = content_map.get(head.content_id)
            if content:
                items.append(
                    ContentItem(
                        head_id=head.id,
                        current_rev_id=head.current_rev_id,
                        current_no=head.current_no,
                        content_id=content.id,
                        project_id=content.project_id,
                        namespace=content.namespace,
                        source_payload=content.source_payload_json,
                        source_lang=content.source_lang,
                        target_lang=head.target_lang,
                        variant_key=head.variant_key,
                    )
                )
        return items

    async def _stream_drafts_query(
        self, session: AsyncSession, batch_size: int, **kwargs: Any
    ) -> list[ThTransHead]:
        """执行查询 'draft' 状态 head 的核心 SQLAlchemy 语句。"""
        stmt = (
            select(ThTransHead)
            .where(ThTransHead.current_status == TranslationStatus.DRAFT.value)
            .order_by(ThTransHead.updated_at)
            .limit(batch_size)
        )
        if kwargs:
            stmt = stmt.with_for_update(**kwargs)
        result = await session.execute(stmt)
        return list(result.scalars().all())

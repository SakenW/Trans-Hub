# packages/server/src/trans_hub/infrastructure/persistence/repositories/_translation_repo.py
"""翻译（修订与头指针）仓库的 SQLAlchemy 实现。"""

from __future__ import annotations
import uuid
from typing import Any, AsyncGenerator

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import NoResultFound

from trans_hub.infrastructure.db._schema import ThContent, ThTransHead, ThTransRev
from trans_hub_core.types import (
    ContentItem,
    TranslationHead,
    TranslationRevision,
    TranslationStatus,
)
from trans_hub_core.uow import ITranslationRepository
from trans_hub_uida import generate_uida
from ._base_repo import BaseRepository


class SqlAlchemyTranslationRepository(BaseRepository, ITranslationRepository):
    """翻译仓库实现。"""

    async def get_revision_by_id(self, revision_id: str) -> TranslationRevision | None:
        """根据 ID 获取一个修订记录的 DTO。"""
        stmt = select(ThTransRev).where(ThTransRev.id == revision_id)
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        return TranslationRevision.from_orm_model(result) if result else None

    async def get_head_by_uida(
        self,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        target_lang: str,
        variant_key: str,
    ) -> TranslationHead | None:
        """根据完整的 UIDA 和翻译维度获取一个翻译头记录的 DTO 对象。"""
        uida = generate_uida(keys)
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
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        return TranslationHead.from_orm_model(result) if result else None

    async def get_head_by_id(self, head_id: str) -> TranslationHead | None:
        """根据 Head ID 获取一个翻译头记录的 DTO 对象。"""
        # ThTransHead 的主键是 (project_id, id)，所以不能用 session.get()
        stmt = select(ThTransHead).where(ThTransHead.id == head_id)
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        return TranslationHead.from_orm_model(result) if result else None

    async def get_head_by_revision(self, revision_id: str) -> TranslationHead | None:
        """根据 revision_id 查找其所属的 head。"""
        stmt = (
            select(ThTransHead)
            .where(
                (ThTransHead.current_rev_id == revision_id)
                | (ThTransHead.published_rev_id == revision_id)
            )
            .limit(1)
        )
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        return TranslationHead.from_orm_model(result) if result else None

    async def get_or_create_head(
        self, project_id: str, content_id: str, target_lang: str, variant_key: str
    ) -> tuple[str, int]:
        """
        在当前事务中获取或创建一个翻译头记录。
        原子性由调用方的 UoW 保证。
        """
        stmt = select(ThTransHead).where(
            ThTransHead.project_id == project_id,
            ThTransHead.content_id == content_id,
            ThTransHead.target_lang == target_lang,
            ThTransHead.variant_key == variant_key,
        )
        existing_head = (await self._session.execute(stmt)).scalar_one_or_none()

        if existing_head:
            return existing_head.id, existing_head.current_no

        # 如果不存在，则创建初始修订 (rev_no=0) 和头指针
        content = await self._session.get(ThContent, content_id)
        if not content:
            raise ValueError(f"内容记录未找到: content_id={content_id}")

        initial_rev = ThTransRev(
            id=str(uuid.uuid4()),
            project_id=project_id,
            content_id=content_id,
            target_lang=target_lang,
            status=TranslationStatus.DRAFT,
            revision_no=0,
            src_payload_json=content.source_payload_json,
        )
        initial_rev.variant_key = variant_key
        self._session.add(initial_rev)
        await self._session.flush()

        new_head = ThTransHead(
            project_id=project_id,
            content_id=content_id,
            target_lang=target_lang,
            current_rev_id=initial_rev.id,
            current_status=TranslationStatus.DRAFT,
            current_no=0,
        )
        new_head.variant_key = variant_key
        
        self._session.add(new_head)
        await self._session.flush()

        return new_head.id, new_head.current_no

    async def create_revision(self, **data: Any) -> str:
        """
        创建一条新的修订，并更新其所属头指针的状态。
        使用事务级别的操作避免会话冲突。
        """
        head_id = data.pop("head_id")
        project_id = data["project_id"]
        content_id = data["content_id"]
        
        # 从data中提取variant_key，因为该字段设置了init=False
        variant_key = data.pop("variant_key", "-")
        
        # 生成新的revision ID
        new_rev_id = str(uuid.uuid4())
        
        # 获取content信息
        content = await self._session.get(ThContent, content_id)
        if not content:
            raise NoResultFound(f"内容记录未找到: content_id={content_id}")
        
        # 创建新revision对象
        new_rev = ThTransRev(
            id=new_rev_id, src_payload_json=content.source_payload_json, **data
        )
        new_rev.variant_key = variant_key
        
        # 添加新revision到会话
        self._session.add(new_rev)
        
        # 使用原生SQL更新head状态，避免ORM会话冲突
        from sqlalchemy import text
        update_stmt = text("""
            UPDATE th_trans_head 
            SET current_rev_id = :new_rev_id,
                current_status = :status,
                current_no = :revision_no
            WHERE id = :head_id AND project_id = :project_id
        """)
        
        await self._session.execute(update_stmt, {
            "new_rev_id": new_rev_id,
            "status": new_rev.status.value,
            "revision_no": new_rev.revision_no,
            "head_id": head_id,
            "project_id": project_id
        })
        
        # flush确保更改被持久化
        await self._session.flush()

        return new_rev_id

    async def get_published_translation(
        self, content_id: str, target_lang: str, variant_key: str
    ) -> tuple[str, dict[str, Any]] | None:
        """获取已发布的译文。"""
        stmt = (
            select(ThTransHead.published_rev_id, ThTransRev.translated_payload_json)
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
        result = (await self._session.execute(stmt)).first()
        return (result[0], result[1]) if result and result[0] is not None else None

    async def stream_drafts(
        self, batch_size: int
    ) -> AsyncGenerator[list[ContentItem], None]:
        """流式获取待处理的 'draft' 状态翻译任务。"""
        while True:
            # 在事务中查询并使用 FOR UPDATE SKIP LOCKED 锁定一批任务
            stmt = (
                select(ThTransHead)
                .where(ThTransHead.current_status == TranslationStatus.DRAFT.value)
                .order_by(ThTransHead.updated_at)
                .limit(batch_size)
                # 预加载关联的 content 以避免 N+1 查询
                .options(selectinload(ThTransHead.content))
                .with_for_update(skip_locked=True)
            )

            result = await self._session.execute(stmt)
            head_results = list(result.scalars().all())

            if not head_results:
                break

            # 将 ORM 对象转换为 DTO
            items = [
                ContentItem(
                    head_id=h.id,
                    current_rev_id=h.current_rev_id,
                    current_no=h.current_no,
                    content_id=h.content.id,
                    project_id=h.content.project_id,
                    namespace=h.content.namespace,
                    source_payload=h.content.source_payload_json,
                    source_lang=h.content.source_lang,
                    target_lang=h.target_lang,
                    variant_key=h.variant_key,
                )
                for h in head_results
                if h.content is not None
            ]

            # 只有在成功转换出 DTO 后才 yield
            if not items:
                break

            yield items

            if len(items) < batch_size:
                break

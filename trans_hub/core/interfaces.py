# trans_hub/core/interfaces.py
# [v2.4 Refactor] 更新持久化层协议，以完全支持 rev/head 模型、状态管理和白皮书 v2.4 的所有读写操作。
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, Protocol

from trans_hub.core.types import TranslationStatus

if TYPE_CHECKING:
    from trans_hub.core.types import ContentItem


class PersistenceHandler(Protocol):
    """定义了白皮书 v2.4 下持久化处理器的纯异步接口协议。"""

    SUPPORTS_NOTIFICATIONS: bool
    _is_sqlite: bool # [新增] 用于策略层判断并发写入能力

    async def connect(self) -> None:
        """建立与数据库的连接。"""
        ...

    async def close(self) -> None:
        """关闭与数据库的连接。"""
        ...

    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[可选] 监听数据库通知，返回通知的负载。"""
        ...

    async def get_content_id_by_uida(
        self, project_id: str, namespace: str, keys_sha256_bytes: bytes
    ) -> str | None:
        """根据 UIDA 的核心三元组，纯粹地读取 content_id。"""
        ...

    async def upsert_content(
        self,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        source_payload: dict[str, Any],
        content_version: int,
    ) -> str:
        """根据 UIDA 幂等地创建或更新 th_content 记录，返回 content_id。"""
        ...
    
    async def get_or_create_translation_head(
        self,
        project_id: str,
        content_id: str,
        target_lang: str,
        variant_key: str,
    ) -> tuple[str, int]:
        """获取或创建一个翻译头记录，返回 (head_id, current_revision_no)。"""
        ...

    async def create_new_translation_revision(
        self,
        *,
        head_id: str,
        project_id: str,
        content_id: str,
        target_lang: str,
        variant_key: str,
        status: TranslationStatus,
        revision_no: int,
        translated_payload: dict[str, Any] | None = None,
        engine_name: str | None = None,
        engine_version: str | None = None,
    ) -> str:
        """在 th_trans_rev 中创建一条新的修订，并更新 th_trans_head 的指针，返回 rev_id。"""
        ...

    async def find_tm_entry(
        self,
        project_id: str,
        namespace: str,
        reuse_sha256_bytes: bytes,
        source_lang: str,
        target_lang: str,
        variant_key: str,
        policy_version: int,
        hash_algo_version: int,
    ) -> tuple[str, dict[str, Any]] | None:
        """在 TM 中查找可复用的翻译，返回 (tm_id, translated_json) 或 None。"""
        ...

    async def upsert_tm_entry(
        self,
        project_id: str,
        namespace: str,
        reuse_sha256_bytes: bytes,
        source_lang: str,
        target_lang: str,
        variant_key: str,
        policy_version: int,
        hash_algo_version: int,
        source_text_json: dict[str, Any],
        translated_json: dict[str, Any],
        quality_score: float,
    ) -> str:
        """幂等地创建或更新 TM 条目，返回 tm_id。"""
        ...
    
    async def link_translation_to_tm(self, translation_rev_id: str, tm_id: str) -> None:
        """在 th_tm_links 中创建一条追溯链接。"""
        ...

    async def get_fallback_order(
        self, project_id: str, locale: str
    ) -> list[str] | None:
        """获取指定项目和语言的回退顺序。"""
        ...
    
    async def get_published_translation(
        self, content_id: str, target_lang: str, variant_key: str
    ) -> tuple[str, dict[str, Any]] | None:
        """获取已发布的译文，返回 (rev_id, translated_payload_json) 或 None。"""
        ...
    
    async def publish_revision(self, revision_id: str) -> bool:
        """将一个 'reviewed' 状态的修订发布，返回是否成功。"""
        ...
        
    async def reject_revision(self, revision_id: str) -> bool:
        """将一个修订的状态标记为 'rejected'，返回是否成功。"""
        ...

    def stream_draft_translations(
        self,
        batch_size: int,
        limit: int | None = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        """流式获取待处理的 'draft' 状态翻译任务。"""
        ...

    async def run_garbage_collection(
        self,
        archived_content_retention_days: int,
        unused_tm_retention_days: int,
        dry_run: bool,
    ) -> dict[str, int]:
        """运行垃圾回收。"""
        ...
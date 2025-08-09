# trans_hub/core/interfaces.py
"""
本模块使用 typing.Protocol 定义了核心组件的接口协议。
此版本已完全升级至 UIDA 架构。
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from trans_hub.core.types import ContentItem, TranslationResult, TranslationStatus


class PersistenceHandler(Protocol):
    """定义了 UIDA 架构下持久化处理器的纯异步接口协议。"""

    SUPPORTS_NOTIFICATIONS: bool

    async def connect(self) -> None:
        """建立与数据库的连接。"""
        ...

    async def close(self) -> None:
        """关闭与数据库的连接。"""
        ...

    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[可选] 监听数据库通知，返回通知的负载。"""
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

    async def create_draft_translation(
        self,
        project_id: str,
        content_id: str,
        target_lang: str,
        variant_key: str,
        source_lang: str | None,
    ) -> str:
        """在 th_translations 中创建一条新的翻译草稿记录，返回 translation_id。"""
        ...

    async def update_translation_from_tm(
        self,
        translation_id: str,
        tm_id: str,
        translated_payload: dict[str, Any],
        status: TranslationStatus = TranslationStatus.DRAFT,
    ) -> None:
        """使用 TM 命中的结果更新翻译记录。"""
        ...

    async def save_translation_results(self, results: list[TranslationResult]) -> None:
        """[Worker专用] 批量保存来自 Worker 处理后的翻译结果。"""
        ...

    async def link_translation_to_tm(self, translation_id: str, tm_id: str) -> None:
        """在 th_tm_links 中创建一条追溯链接。"""
        ...

    async def get_published_translation(
        self, content_id: str, target_lang: str, variant_key: str
    ) -> dict[str, Any] | None:
        """获取指定维度的已发布译文，返回 translated_payload_json 或 None。"""
        ...

    def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: int | None = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        """流式获取待处理的翻译任务。"""
        ...

    async def reset_stale_tasks(self) -> None:
        """[Worker专用] 在启动时重置所有处于“TRANSLATING”状态的旧任务为草稿。"""
        ...

    async def run_garbage_collection(
        self,
        archived_content_retention_days: int,
        unused_tm_retention_days: int,
        dry_run: bool = False,
    ) -> dict[str, int]:
        """
        [新] 运行垃圾回收，清理已归档的内容和长期未使用的 TM 条目。
        返回一个包含被删除项目计数的报告。
        """
        ...
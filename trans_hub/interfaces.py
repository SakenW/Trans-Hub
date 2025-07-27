# trans_hub/interfaces.py
"""
本模块使用 typing.Protocol 定义了核心组件的接口协议。

这些纯异步接口是依赖倒置原则（DIP）的基石，确保核心逻辑与具体实现解耦。
"""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager
from typing import Any, Optional, Protocol

import aiosqlite  # 导入以用于类型提示

from trans_hub.types import (
    ContentItem,
    TranslationResult,
    TranslationStatus,
)


class PersistenceHandler(Protocol):
    """
    定义了持久化处理器的纯异步接口协议。

    任何实现了此协议的类都可以作为 Trans-Hub 的数据存储层。
    """

    async def connect(self) -> None:
        """建立与数据存储的连接。"""
        ...

    async def close(self) -> None:
        """关闭与数据存储的连接。"""
        ...

    def transaction(self) -> AbstractAsyncContextManager[aiosqlite.Cursor]:
        """
        提供一个异步事务上下文管理器。

        返回:
            一个异步上下文管理器，其产出值为数据库游标。
        """
        ...

    async def reset_stale_tasks(self) -> None:
        """重置所有处于“正在翻译”状态的僵尸任务，实现系统自愈。"""
        ...

    def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        """
        以异步生成器的方式，分批流式获取待翻译的内容项。

        参数:
            lang_code: 目标语言代码。
            statuses: 要获取的任务状态列表 (例如 PENDING, FAILED)。
            batch_size: 每个批次的大小。
            limit: 总共获取的最大数量。

        返回:
            一个异步生成器，每次产出 `ContentItem` 列表。
        """
        ...

    async def ensure_pending_translations(
        self,
        text_content: str,
        target_langs: list[str],
        source_lang: Optional[str],
        engine_version: str,
        business_id: Optional[str] = None,
        context_hash: Optional[str] = None,
        context_json: Optional[str] = None,
        force_retranslate: bool = False,
    ) -> None:
        """
        确保指定的翻译任务存在于数据库中，如果不存在则创建为 PENDING 状态。

        如果 `force_retranslate` 为 True，则将已存在的任务状态重置为 PENDING。
        """
        ...

    async def save_translations(self, results: list[TranslationResult]) -> None:
        """将一批翻译结果批量保存到数据存储中。"""
        ...

    async def get_translation(
        self,
        text_content: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        """根据原文、目标语言和上下文，获取一个已完成的翻译结果。"""
        ...

    async def get_business_id_for_content(
        self, content_id: int, context_hash: str
    ) -> Optional[str]:
        """根据内容ID和上下文哈希查找关联的业务ID。"""
        ...

    async def touch_source(self, business_id: str) -> None:
        """更新指定业务ID的 `last_seen_at` 时间戳，用于垃圾回收判断。"""
        ...

    async def garbage_collect(
        self, retention_days: int, dry_run: bool = False
    ) -> dict[str, int]:
        """
        执行垃圾回收，清理过期或孤立的数据。

        返回:
            一个字典，包含被删除的各类记录的数量。
        """
        ...

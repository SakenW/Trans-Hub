# packages/server/tests/helpers/factories/tui_factories.py
"""
为 Textual TUI 提供可预测的、结构化的模拟数据。
"""
import uuid
from datetime import datetime, timezone
from itertools import cycle

from trans_hub.presentation.tui.state import TranslationDetail
from trans_hub_core.types import (
    Comment,
    TranslationHead,
    TranslationRevision,
    TranslationStatus,
)

STATUS_CYCLE = cycle([
    TranslationStatus.PUBLISHED,
    TranslationStatus.REVIEWED,
    TranslationStatus.DRAFT,
    TranslationStatus.REJECTED,
])

def create_fake_heads(count: int) -> list[TranslationHead]:
    """创建一批模拟的 TranslationHead 对象。"""
    return [
        TranslationHead(
            id=str(uuid.uuid4()),
            project_id=f"proj-{(i % 3) + 1}",
            content_id=f"content-{uuid.uuid4().hex[:8]}",
            target_lang=cycle(["de", "fr", "ja"]).__next__(),
            variant_key=cycle(["-", "dark-mode"]).__next__(),
            current_rev_id=str(uuid.uuid4()),
            current_status=STATUS_CYCLE.__next__(),
            current_no=i % 5,
            published_rev_id=str(uuid.uuid4()) if i % 2 == 0 else None,
            published_no=i % 5 if i % 2 == 0 else None,
            published_at=datetime.now(timezone.utc) if i % 2 == 0 else None,
        )
        for i in range(count)
    ]

def create_fake_revisions(head: TranslationHead, count: int) -> list[TranslationRevision]:
    """为给定的 Head 创建一批模拟的 TranslationRevision。"""
    return [
        TranslationRevision(
            id=head.current_rev_id if i == head.current_no else str(uuid.uuid4()),
            project_id=head.project_id,
            content_id=head.content_id,
            status=head.current_status if i == head.current_no else TranslationStatus.REVIEWED,
            revision_no=i,
            translated_payload_json={"text": f"Translated text for rev {i}"},
            engine_name="fake-engine",
            engine_version="1.0",
        )
        for i in range(head.current_no + 1)
    ]

def create_fake_comments(head: TranslationHead, count: int) -> list[Comment]:
    """为给定的 Head 创建一批模拟的 Comment。"""
    return [
        Comment(
            id=str(i),
            head_id=head.id,
            project_id=head.project_id,
            author=f"user-{(i % 2) + 1}",
            body=f"This is comment number {i+1}.",
            created_at=datetime.now(timezone.utc),
        )
        for i in range(count)
    ]

def create_fake_details(head: TranslationHead) -> TranslationDetail:
    """创建一个完整的 TranslationDetail 模拟对象。"""
    return TranslationDetail(
        head=head,
        revisions=create_fake_revisions(head, head.current_no + 1),
        comments=create_fake_comments(head, 3),
    )
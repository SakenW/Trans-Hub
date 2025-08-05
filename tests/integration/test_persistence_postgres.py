# tests/integration/test_persistence_postgres.py
"""
针对 `trans_hub.persistence.postgres` 的集成测试。

这些测试需要在环境变量 `TH_TEST_POSTGRES_DSN` 中指定一个可用的
PostgreSQL 数据库连接字符串来运行。
"""

import pytest

from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.core.types import TranslationStatus


@pytest.mark.asyncio
async def test_pg_ensure_content_and_context_creates_all_entities(
    postgres_handler: PersistenceHandler,
) -> None:
    """测试 ensure_content_and_context 是否能正确创建所有实体。"""
    business_id = "test.pg.hello"
    source_payload = {"text": "Hello PG"}
    context = {"domain": "testing"}

    content_id, context_id = await postgres_handler.ensure_content_and_context(
        business_id=business_id,
        source_payload=source_payload,
        context=context,
    )
    assert content_id is not None
    assert context_id is not None

    # 验证第二次调用返回相同ID
    content_id2, context_id2 = await postgres_handler.ensure_content_and_context(
        business_id=business_id,
        source_payload=source_payload,
        context=context,
    )
    assert content_id == content_id2
    assert context_id == context_id2


@pytest.mark.asyncio
async def test_pg_create_pending_translations_and_force_retranslate(
    postgres_handler: PersistenceHandler,
) -> None:
    """测试创建待处理任务和强制重译的逻辑。"""
    business_id = "test.pg.force"
    content_id, _ = await postgres_handler.ensure_content_and_context(
        business_id, {"text": "force me"}, None
    )

    # 1. 首次创建
    await postgres_handler.create_pending_translations(
        content_id, None, ["de"], "en", "1.0", force_retranslate=False
    )
    result1 = await postgres_handler.find_translation(business_id, "de")
    assert result1 is not None
    assert result1.status == TranslationStatus.PENDING

    # 2. 模拟翻译完成
    result1.status = TranslationStatus.TRANSLATED
    result1.translated_payload = {"text": "zwing mich"}
    await postgres_handler.save_translation_results([result1])
    
    # 3. 强制重译
    await postgres_handler.create_pending_translations(
        content_id, None, ["de"], "en", "1.1", force_retranslate=True
    )
    result2 = await postgres_handler.find_translation(business_id, "de")
    assert result2 is not None
    assert result2.status == TranslationStatus.PENDING
    assert result2.translated_payload is None # 应被清空

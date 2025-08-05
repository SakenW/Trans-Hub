# tests/integration/test_persistence_postgres.py
"""
针对 `trans_hub.persistence.postgres` 的集成测试。

这些测试需要在 .env 文件或环境变量中将 TH_DATABASE_URL 设置为
一个可用的 PostgreSQL 连接字符串来运行。
"""
import pytest

from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.core.types import TranslationResult, TranslationStatus
from tests.integration.conftest import requires_postgres

# 将标记应用到整个模块的所有测试
pytestmark = requires_postgres


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

    source_payload_updated = {"text": "Hello PG Updated"}
    content_id2, context_id2 = await postgres_handler.ensure_content_and_context(
        business_id=business_id,
        source_payload=source_payload_updated,
        context=context,
    )
    assert content_id == content_id2
    assert context_id == context_id2


@pytest.mark.asyncio
async def test_pg_create_pending_translations_and_force_retranslate(
    postgres_handler: PersistenceHandler,
) -> None:
    """测试创建待处理任务和强制重译的逻辑。"""
    from trans_hub.persistence.postgres import PostgresPersistenceHandler
    business_id = "test.pg.force"
    content_id, _ = await postgres_handler.ensure_content_and_context(
        business_id, {"text": "force me"}, None
    )

    await postgres_handler.create_pending_translations(
        content_id, None, ["de"], "en", "1.0", force_retranslate=False
    )
    result1 = await postgres_handler.find_translation(business_id, "de")
    assert result1 is not None
    assert result1.status == TranslationStatus.PENDING

    # 模拟 Worker 拉取任务，状态变为 TRANSLATING
    handler = postgres_handler
    assert isinstance(handler, PostgresPersistenceHandler)
    async with handler.pool.acquire() as conn:
        await conn.execute(
            "UPDATE th_translations SET status = $1 WHERE id = $2",
            TranslationStatus.TRANSLATING.value,
            result1.translation_id,
        )

    # 模拟翻译完成
    result_to_save = TranslationResult(
        translation_id=result1.translation_id,
        business_id=business_id,
        original_payload={"text": "force me"},
        translated_payload={"text": "zwing mich"},
        target_lang="de",
        status=TranslationStatus.TRANSLATED, # v3.28 修复：这里的 status 就是要保存到数据库的最终状态
        from_cache=False,
        context_hash="__GLOBAL__",
        engine="test-engine",
    )
    await postgres_handler.save_translation_results([result_to_save])
    
    result_saved = await postgres_handler.find_translation(business_id, "de")
    assert result_saved is not None
    assert result_saved.status == TranslationStatus.TRANSLATED

    # 测试强制重译
    await postgres_handler.create_pending_translations(
        content_id, None, ["de"], "en", "1.1", force_retranslate=True
    )
    result2 = await postgres_handler.find_translation(business_id, "de")
    assert result2 is not None
    assert result2.status == TranslationStatus.PENDING
    assert result2.translated_payload is None
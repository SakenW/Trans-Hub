# tests/integration/test_persistence_uida.py
"""
对白皮书 v1.2 持久化层的集成测试。
"""
from __future__ import annotations

import pytest

from tests.helpers.factories import TEST_NAMESPACE, TEST_PROJECT_ID
from trans_hub._uida.reuse_key import build_reuse_sha256
from trans_hub.core.interfaces import PersistenceHandler

pytestmark = pytest.mark.asyncio


async def test_upsert_content_is_idempotent(handler: PersistenceHandler):
    """测试 `upsert_content` 的幂等性。"""
    project_id = TEST_PROJECT_ID
    namespace = TEST_NAMESPACE
    keys = {"view": "home", "id": "title"}
    source_payload = {"text": "Welcome Home"}
    
    content_id_1 = await handler.upsert_content(
        project_id, namespace, keys, source_payload, content_version=1
    )
    content_id_2 = await handler.upsert_content(
        project_id, namespace, keys, source_payload, content_version=1
    )
    
    assert content_id_1 == content_id_2


async def test_find_and_upsert_tm_entry(handler: PersistenceHandler):
    """测试 TM 条目的完整生命周期：查找（未命中）、创建、再次查找（命中）。"""
    project_id = TEST_PROJECT_ID
    namespace = "tm.test.v1"
    source_lang = "en"
    target_lang = "de"
    variant_key = "-"
    policy_version = 1
    hash_algo_version = 1
    source_text_json = {"text": "Login"}
    translated_payload = {"text": "Anmelden"}
    
    reuse_sha = build_reuse_sha256(
        namespace=namespace,
        reduced_keys={},
        source_fields=source_text_json,
    )

    # 1. 初始查找，应未命中
    entry = await handler.find_tm_entry(
        project_id, namespace, reuse_sha, source_lang, target_lang,
        variant_key, policy_version, hash_algo_version
    )
    assert entry is None

    # 2. 创建 TM 条目
    tm_id = await handler.upsert_tm_entry(
        project_id, namespace, reuse_sha, source_lang, target_lang,
        variant_key, policy_version, hash_algo_version,
        source_text_json=source_text_json,
        translated_json=translated_payload,
        quality_score=0.95
    )
    assert isinstance(tm_id, str)

    # 3. 再次查找，应命中
    entry_hit = await handler.find_tm_entry(
        project_id, namespace, reuse_sha, source_lang, target_lang,
        variant_key, policy_version, hash_algo_version
    )
    assert entry_hit is not None
    hit_id, hit_payload = entry_hit
    assert hit_id == tm_id
    assert hit_payload == translated_payload


async def test_stream_draft_translations(handler: PersistenceHandler):
    """测试 `stream_draft_translations` 能否正确获取草稿任务。"""
    # 1. 创建内容和草稿
    content_id = await handler.upsert_content(
        TEST_PROJECT_ID, TEST_NAMESPACE, {"k": "v"}, {"text": "t"}, 1
    )
    await handler.create_draft_translation(
        TEST_PROJECT_ID, content_id, "de", "-", "en"
    )
    await handler.create_draft_translation(
        TEST_PROJECT_ID, content_id, "fr", "-", "en"
    )

    # 2. 流式获取
    all_items = []
    async for batch in handler.stream_draft_translations(batch_size=10):
        all_items.extend(batch)
    
    assert len(all_items) == 2
    langs = {item.target_lang for item in all_items}
    assert langs == {"de", "fr"}


async def test_link_translation_to_tm(handler: PersistenceHandler):
    """测试 `link_translation_to_tm` 能否正确创建追溯链接。"""
    content_id = await handler.upsert_content(
        TEST_PROJECT_ID, "links.test", {"k": "v"}, {"text": "t"}, 1
    )
    translation_id = await handler.create_draft_translation(
        TEST_PROJECT_ID, content_id, "fr", "-", "en"
    )
    reuse_sha = build_reuse_sha256(namespace="links.test", reduced_keys={}, source_fields={"text": "t"})
    tm_id = await handler.upsert_tm_entry(
        TEST_PROJECT_ID, "links.test", reuse_sha, "en", "fr", "-", 1, 1, {"text": "t"}, {"text": "t_fr"}, 1.0
    )

    # 创建链接并验证
    await handler.link_translation_to_tm(translation_id, tm_id)
    # 再次创建，由于唯一约束，不应报错
    await handler.link_translation_to_tm(translation_id, tm_id)
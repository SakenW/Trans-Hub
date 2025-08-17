# packages/server/tests/integration/application/test_app_flow.py
"""
对 Coordinator 驱动的核心业务流程进行集成测试。
"""
import uuid # [最终修复]
import pytest
from sqlalchemy import select
from trans_hub.application.coordinator import Coordinator
# [最终修复] 补全所有需要的 ORM 模型和领域模块的导入
from trans_hub.domain import tm as tm_domain
from trans_hub.infrastructure.db._schema import ThProjects, ThTransRev, ThTmUnits, ThTmLinks
from trans_hub_core.types import TranslationStatus
from tests.helpers.factories import create_request_data

pytestmark = [pytest.mark.db, pytest.mark.integration]


@pytest.mark.asyncio
async def test_full_request_publish_get_flow(coordinator: Coordinator):
    """
    测试从请求 -> (模拟处理) -> 发布 -> 获取的完整快乐路径。
    """
    req_data = create_request_data(target_langs=["de"])
    await coordinator.request_translation(**req_data)
    head = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys=req_data["keys"], target_lang="de", variant_key="-"
    )
    assert head is not None
    assert head.current_status == TranslationStatus.DRAFT
    rev_id = await coordinator.handler.create_new_translation_revision(
        head_id=head.id, project_id=head.project_id, content_id=head.content_id,
        target_lang=head.target_lang, variant_key=head.variant_key,
        status=TranslationStatus.REVIEWED, revision_no=head.current_no + 1,
        translated_payload_json={"text": "Hallo Welt"},
    )
    assert rev_id is not None
    success = await coordinator.publish_translation(rev_id)
    assert success is True
    result = await coordinator.get_translation(
        project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys=req_data["keys"], target_lang="de"
    )
    assert result is not None
    assert result["text"] == "Hallo Welt"


@pytest.mark.asyncio
async def test_language_fallback_flow(coordinator: Coordinator):
    """测试语言回退链是否按预期工作。"""
    req_data = create_request_data(target_langs=["de"], keys={"id": "fallback_test"})
    content_id = await coordinator.request_translation(**req_data)
    head_de = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys=req_data["keys"], target_lang="de", variant_key="-"
    )
    assert head_de is not None
    rev_id_de = await coordinator.handler.create_new_translation_revision(
        head_id=head_de.id, project_id=req_data["project_id"], content_id=content_id,
        target_lang="de", variant_key="-", status=TranslationStatus.REVIEWED,
        revision_no=head_de.current_no + 1, translated_payload_json={"text": "Hallo aus Deutschland"},
    )
    await coordinator.publish_translation(rev_id_de)
    await coordinator.handler.set_fallback_order(
        project_id=req_data["project_id"], locale="de-CH", fallback_order=["de"],
    )
    result = await coordinator.get_translation(
        project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys=req_data["keys"], target_lang="de-CH"
    )
    assert result is not None
    assert result["text"] == "Hallo aus Deutschland"


@pytest.mark.asyncio
async def test_commenting_flow(coordinator: Coordinator):
    """测试添加和获取评论的端到端流程。"""
    req_data = create_request_data(target_langs=["fr"], keys={"id": "comment_test"})
    await coordinator.request_translation(**req_data)
    head = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys=req_data["keys"], target_lang="fr", variant_key="-"
    )
    assert head is not None
    comment_body = "这条翻译需要更多上下文。"
    comment_id = await coordinator.add_comment(head.id, "reviewer-1", comment_body)
    assert isinstance(comment_id, str)
    comments = await coordinator.get_comments(head.id)
    assert len(comments) == 1
    assert comments[0].body == comment_body
    assert comments[0].author == "reviewer-1"


@pytest.mark.asyncio
async def test_unpublish_flow(coordinator: Coordinator):
    """
    测试 "Request -> Publish -> Unpublish -> Get" 的完整流程。
    """
    req_data = create_request_data(target_langs=["es"], keys={"id": "unpublish-test"})
    content_id = await coordinator.request_translation(**req_data)
    head_info = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys=req_data["keys"], target_lang="es", variant_key="-"
    )
    assert head_info is not None
    rev_id = await coordinator.handler.create_new_translation_revision(
        head_id=head_info.id, project_id=head_info.project_id, content_id=content_id,
        target_lang="es", variant_key="-", status=TranslationStatus.REVIEWED,
        revision_no=1, translated_payload_json={"text": "Hola Mundo"}
    )
    await coordinator.publish_translation(rev_id)
    published_head = await coordinator.handler.get_head_by_id(head_info.id)
    assert published_head is not None
    assert published_head.published_rev_id == rev_id
    success = await coordinator.unpublish_translation(rev_id, actor="test-admin")
    assert success is True
    unpublished_head = await coordinator.handler.get_head_by_id(head_info.id)
    assert unpublished_head is not None
    assert unpublished_head.published_rev_id is None
    assert unpublished_head.current_status == TranslationStatus.REVIEWED
    result = await coordinator.get_translation(
        project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys=req_data["keys"], target_lang="es"
    )
    assert result is None


@pytest.mark.asyncio
async def test_reject_flow(coordinator: Coordinator):
    """
    测试 "Request -> (Review) -> Reject" 的流程。
    """
    req_data = create_request_data(target_langs=["ja"], keys={"id": "reject-test"})
    content_id = await coordinator.request_translation(**req_data)
    head_info = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys=req_data["keys"], target_lang="ja", variant_key="-"
    )
    assert head_info is not None
    reviewed_rev_id = await coordinator.handler.create_new_translation_revision(
        head_id=head_info.id, project_id=head_info.project_id, content_id=content_id,
        target_lang="ja", variant_key="-", status=TranslationStatus.REVIEWED,
        revision_no=1, translated_payload_json={"text": "こんにちは世界"}
    )
    head_before_reject = await coordinator.handler.get_head_by_id(head_info.id)
    assert head_before_reject is not None
    assert head_before_reject.current_status == TranslationStatus.REVIEWED
    success = await coordinator.reject_translation(reviewed_rev_id, actor="test-reviewer")
    assert success is True
    head_after_reject = await coordinator.handler.get_head_by_id(head_info.id)
    assert head_after_reject is not None
    assert head_after_reject.current_status == TranslationStatus.REJECTED
    async with coordinator._sessionmaker() as session:
        rev = (await session.execute(
            select(ThTransRev).where(ThTransRev.id == reviewed_rev_id)
        )).scalar_one()
        assert rev.status == TranslationStatus.REJECTED

@pytest.mark.asyncio
async def test_tm_hit_flow(coordinator: Coordinator):
    """
    [新增] 验证当 TM 命中时，系统是否直接创建 'reviewed' 修订。
    """
    # 1. 准备：手动创建一个 TM 条目
    project_id = "tm-hit-proj"
    namespace = "tm.test"
    source_lang = "en"
    target_lang = "de"
    source_payload = {"text": "Hello TM World"}
    translated_payload = {"text": "Hallo TM-Welt"}
    keys = {"id": "tm-hit-key"}

    # 计算 TM 复用键
    source_fields = {"text": tm_domain.normalize_text_for_tm(source_payload["text"])}
    reuse_sha = tm_domain.build_reuse_key(namespace=namespace, reduced_keys={}, source_fields=source_fields)

    async with coordinator._sessionmaker.begin() as session:
        # 确保项目存在
        session.add(ThProjects(project_id=project_id, display_name="TM Hit Test"))
        # 创建 TM 条目
        session.add(ThTmUnits(
            id=str(uuid.uuid4()), project_id=project_id, namespace=namespace,
            src_lang=source_lang, tgt_lang=target_lang, src_hash=reuse_sha,
            src_payload=source_payload, tgt_payload=translated_payload
        ))

    # 2. 行动：提交一个与 TM 条目匹配的翻译请求
    req_data = create_request_data(
        project_id=project_id, namespace=namespace, keys=keys,
        source_payload=source_payload, target_langs=[target_lang]
    )
    await coordinator.request_translation(**req_data)

    # 3. 验证
    head = await coordinator.handler.get_translation_head_by_uida(
        project_id=project_id, namespace=namespace, keys=keys,
        target_lang=target_lang, variant_key="-"
    )
    assert head is not None
    
    # 3a. [核心断言] Head 的当前状态应该是 'reviewed'，而不是 'draft'
    assert head.current_status == TranslationStatus.REVIEWED, \
        "TM 命中时，应该直接创建 reviewed 状态的修订"
    
    # 3b. [核心断言] 修订号应该是 1 (初始的 draft(0) 被跳过，直接创建了 reviewed(1))
    # *Self-Correction*: 我们的 get_or_create 总是会先创建一个 rev_no=0 的 draft。
    # TM 命中后，会立刻创建一个 rev_no=1 的 reviewed。所以 current_no 应该是 1。
    assert head.current_no == 1, "TM 命中后，Head 应指向 revision_no=1"

    async with coordinator._sessionmaker() as session:
        # 3c. 验证新修订的内容
        new_rev = (await session.get(ThTransRev, (project_id, head.current_rev_id)))
        assert new_rev is not None
        assert new_rev.translated_payload_json["text"] == "Hallo TM-Welt"
        assert new_rev.origin_lang == "tm", "修订的来源应标记为 'tm'"

        # 3d. 验证溯源链接已创建
        link = (await session.execute(
            select(ThTmLinks).where(ThTmLinks.translation_rev_id == new_rev.id)
        )).scalar_one_or_none()
        assert link is not None, "应该为 TM 命中创建溯源链接"
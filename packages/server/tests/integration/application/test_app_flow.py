# packages/server/tests/integration/application/test_app_flow.py
"""
对 Coordinator 驱动的核心业务流程进行集成测试 (UoW 重构版)。
"""

import pytest
from trans_hub.application.coordinator import Coordinator
from trans_hub.domain import tm as tm_domain
from trans_hub_core.types import TranslationStatus
from tests.helpers.factories import create_request_data

pytestmark = [pytest.mark.db, pytest.mark.integration]


@pytest.mark.asyncio
async def test_full_request_publish_get_flow(coordinator: Coordinator):
    """
    测试从请求 -> (模拟处理) -> 发布 -> 获取的完整快乐路径。
    """
    # 1. 准备 & 行动: 提交请求
    req_data = create_request_data(target_langs=["de"])
    content_id = await coordinator.request_translation(**req_data)

    # 2. 准备 & 行动: 模拟 Worker 处理并创建 'reviewed' 修订
    # 在 UoW 架构下，这部分逻辑在 coordinator 外部，可以直接调用仓库
    async with coordinator._uow_factory() as uow:
        head = await uow.translations.get_head_by_uida(
            project_id=req_data["project_id"],
            namespace=req_data["namespace"],
            keys=req_data["keys"],
            target_lang="de",
            variant_key="-",
        )
        assert head and head.current_status == TranslationStatus.DRAFT

        rev_id = await uow.translations.create_revision(
            head_id=head.id,
            project_id=head.project_id,
            content_id=content_id,
            target_lang="de",
            variant_key="-",
            status=TranslationStatus.REVIEWED,
            revision_no=head.current_no + 1,
            translated_payload_json={"text": "Hallo Welt"},
        )

    # 3. 行动: 发布
    success = await coordinator.publish_translation(rev_id)
    assert success is True

    # 4. 验证
    result = await coordinator.get_translation(
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys=req_data["keys"],
        target_lang="de",
    )
    assert result is not None
    assert result["text"] == "Hallo Welt"


@pytest.mark.asyncio
async def test_language_fallback_flow(coordinator: Coordinator):
    """测试语言回退链是否按预期工作。"""
    # 1. 准备
    req_data = create_request_data(target_langs=["de"], keys={"id": "fallback_test"})
    content_id = await coordinator.request_translation(**req_data)

    # 1a. 发布一个德语版本
    async with coordinator._uow_factory() as uow:
        head_de = await uow.translations.get_head_by_uida(
            project_id=req_data["project_id"],
            namespace=req_data["namespace"],
            keys=req_data["keys"],
            target_lang="de",
            variant_key="-",
        )
        assert head_de is not None
        rev_id_de = await uow.translations.create_revision(
            head_id=head_de.id,
            project_id=req_data["project_id"],
            content_id=content_id,
            target_lang="de",
            variant_key="-",
            status=TranslationStatus.REVIEWED,
            revision_no=head_de.current_no + 1,
            translated_payload_json={"text": "Hallo aus Deutschland"},
        )
    await coordinator.publish_translation(rev_id_de)

    # 1b. 设置回退链
    async with coordinator._uow_factory() as uow:
        await uow.misc.set_fallback_order(
            project_id=req_data["project_id"],
            locale="de-CH",
            fallback_order=["de"],
        )

    # 2. 行动: 请求一个不存在的语言 (de-CH)
    result = await coordinator.get_translation(
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys=req_data["keys"],
        target_lang="de-CH",
    )

    # 3. 验证: 应该回退到德语
    assert result is not None
    assert result["text"] == "Hallo aus Deutschland"


@pytest.mark.asyncio
async def test_commenting_flow(coordinator: Coordinator):
    """测试添加和获取评论的端到端流程。"""
    # 1. 准备: 提交一个请求以获取 head_id
    req_data = create_request_data(target_langs=["fr"], keys={"id": "comment_test"})
    await coordinator.request_translation(**req_data)

    async with coordinator._uow_factory() as uow:
        head = await uow.translations.get_head_by_uida(
            project_id=req_data["project_id"],
            namespace=req_data["namespace"],
            keys=req_data["keys"],
            target_lang="fr",
            variant_key="-",
        )
        assert head is not None
        head_id = head.id

    # 2. 行动: 添加评论
    comment_body = "这条翻译需要更多上下文。"
    comment_id = await coordinator.add_comment(head_id, "reviewer-1", comment_body)
    assert isinstance(comment_id, str)

    # 3. 验证: 获取评论并检查内容
    comments = await coordinator.get_comments(head_id)
    assert len(comments) == 1
    assert comments[0].body == comment_body
    assert comments[0].author == "reviewer-1"


@pytest.mark.asyncio
async def test_unpublish_flow(coordinator: Coordinator):
    """测试 "Request -> Publish -> Unpublish -> Get" 的完整流程。"""
    # 1. 准备: 提交并发布一个翻译
    req_data = create_request_data(target_langs=["es"], keys={"id": "unpublish-test"})
    content_id = await coordinator.request_translation(**req_data)

    async with coordinator._uow_factory() as uow:
        head_info = await uow.translations.get_head_by_uida(
            project_id=req_data["project_id"],
            namespace=req_data["namespace"],
            keys=req_data["keys"],
            target_lang="es",
            variant_key="-",
        )
        assert head_info is not None
        rev_id = await uow.translations.create_revision(
            head_id=head_info.id,
            project_id=head_info.project_id,
            content_id=content_id,
            target_lang="es",
            variant_key="-",
            status=TranslationStatus.REVIEWED,
            revision_no=1,
            translated_payload_json={"text": "Hola Mundo"},
        )
    await coordinator.publish_translation(rev_id)

    # 验证发布成功
    async with coordinator._uow_factory() as uow:
        published_head = await uow.translations.get_head_by_id(head_info.id)
        assert published_head and published_head.published_rev_id == rev_id

    # 2. 行动: 撤回发布
    success = await coordinator.unpublish_translation(rev_id, actor="test-admin")
    assert success is True

    # 3. 验证:
    # 3a. 检查 head 状态
    async with coordinator._uow_factory() as uow:
        unpublished_head = await uow.translations.get_head_by_id(head_info.id)
        assert unpublished_head and unpublished_head.published_rev_id is None
        assert unpublished_head.current_status == TranslationStatus.REVIEWED

    # 3b. 尝试获取翻译，应该返回 None
    result = await coordinator.get_translation(
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys=req_data["keys"],
        target_lang="es",
    )
    assert result is None


@pytest.mark.asyncio
async def test_reject_flow(coordinator: Coordinator):
    """测试 "Request -> (Review) -> Reject" 的流程。"""
    # 1. 准备: 提交并创建一个 'reviewed' 修订
    req_data = create_request_data(target_langs=["ja"], keys={"id": "reject-test"})
    content_id = await coordinator.request_translation(**req_data)

    async with coordinator._uow_factory() as uow:
        head_info = await uow.translations.get_head_by_uida(
            project_id=req_data["project_id"],
            namespace=req_data["namespace"],
            keys=req_data["keys"],
            target_lang="ja",
            variant_key="-",
        )
        assert head_info is not None
        reviewed_rev_id = await uow.translations.create_revision(
            head_id=head_info.id,
            project_id=head_info.project_id,
            content_id=content_id,
            target_lang="ja",
            variant_key="-",
            status=TranslationStatus.REVIEWED,
            revision_no=1,
            translated_payload_json={"text": "こんにちは世界"},
        )
        head_before_reject = await uow.translations.get_head_by_id(head_info.id)
        assert (
            head_before_reject
            and head_before_reject.current_status == TranslationStatus.REVIEWED
        )

    # 2. 行动: 拒绝修订
    success = await coordinator.reject_translation(
        reviewed_rev_id, actor="test-reviewer"
    )
    assert success is True

    # 3. 验证: 检查 head 和 revision 的状态
    async with coordinator._uow_factory() as uow:
        head_after_reject = await uow.translations.get_head_by_id(head_info.id)
        assert (
            head_after_reject
            and head_after_reject.current_status == TranslationStatus.REJECTED
        )

        # 假设仓库有一个 get_revision_by_id 方法
        rev = await uow.translations.get_revision_by_id(reviewed_rev_id)
        assert rev and rev.status == TranslationStatus.REJECTED


@pytest.mark.asyncio
async def test_tm_hit_flow(coordinator: Coordinator):
    """验证当 TM 命中时，系统是否直接创建 'reviewed' 修订。"""
    # 1. 准备：手动创建一个 TM 条目
    project_id = "tm-hit-proj"
    namespace = "tm.test"
    source_payload = {"text": "Hello TM World"}
    translated_payload = {"text": "Hallo TM-Welt"}
    keys = {"id": "tm-hit-key"}

    source_fields = {"text": tm_domain.normalize_text_for_tm(source_payload["text"])}
    reuse_sha = tm_domain.build_reuse_key(
        namespace=namespace, reduced_keys={}, source_fields=source_fields
    )

    async with coordinator._uow_factory() as uow:
        await uow.misc.add_project_if_not_exists(project_id, "TM Hit Test")
        await uow.tm.upsert_entry(
            project_id=project_id,
            namespace=namespace,
            src_lang="en",
            tgt_lang="de",
            src_hash=reuse_sha,
            src_payload=source_payload,
            tgt_payload=translated_payload,
        )

    # 2. 行动：提交一个与 TM 条目匹配的翻译请求
    req_data = create_request_data(
        project_id=project_id,
        namespace=namespace,
        keys=keys,
        source_payload=source_payload,
        target_langs=["de"],
    )
    await coordinator.request_translation(**req_data)

    # 3. 验证
    async with coordinator._uow_factory() as uow:
        head = await uow.translations.get_head_by_uida(
            project_id=project_id,
            namespace=namespace,
            keys=keys,
            target_lang="de",
            variant_key="-",
        )
        assert head is not None
        assert head.current_status == TranslationStatus.REVIEWED
        assert head.current_no == 1

        new_rev = await uow.translations.get_revision_by_id(head.current_rev_id)
        assert new_rev
        assert new_rev.translated_payload_json["text"] == "Hallo TM-Welt"
        assert new_rev.origin_lang == "tm"

        link_exists = await uow.tm.check_link_exists(new_rev.id)  # 假设有此方法
        assert link_exists

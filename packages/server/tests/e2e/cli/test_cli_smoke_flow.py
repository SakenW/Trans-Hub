# packages/server/tests/e2e/cli/test_cli_smoke_flow.py
"""
对 CLI 进行端到端的冒烟测试，覆盖完整的生命周期。
"""
import json
import uuid
import pytest
from unittest.mock import MagicMock

from sqlalchemy import select
from tests.helpers.factories import create_request_data
from trans_hub.application.coordinator import Coordinator
from trans_hub.infrastructure.db._schema import ThTransHead, ThTransRev
from trans_hub.presentation.cli.commands import request as request_cmd
from trans_hub.presentation.cli.commands import status as status_cmd
from trans_hub.presentation.cli._state import CLISharedState
from trans_hub_core.types import TranslationStatus

pytestmark = [pytest.mark.e2e, pytest.mark.slow]


@pytest.fixture
def mock_cli_context(coordinator: Coordinator) -> MagicMock:
    """
    创建一个模拟的 Typer Context，它包含了由 pytest-asyncio 
    管理的、已完全初始化的 coordinator 实例。
    """
    mock = MagicMock()
    mock.obj = CLISharedState(config=coordinator.config)
    return mock


@pytest.mark.asyncio
async def test_cli_full_lifecycle_flow(
    coordinator: Coordinator,
    mock_cli_context: MagicMock,
    capsys,
):
    """
    测试通过 CLI 驱动的 "Request -> Publish -> Unpublish -> Reject" 完整闭环。
    """
    # === 阶段 1: Request -> Publish -> Get (与之前版本相同) ===
    
    # 1a. 准备
    req_data = create_request_data(target_langs=["ja"], keys={"id": f"cli-e2e-full-{uuid.uuid4().hex[:6]}"})
    
    # 1b. 提交请求
    await request_cmd.request_new(
        ctx=mock_cli_context, project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys_json=json.dumps(req_data["keys"]), source_payload_json=json.dumps(req_data["source_payload"]),
        target_langs=["ja"],
    )
    assert "翻译请求已成功提交" in capsys.readouterr().out

    # 1c. 幕后操作: 模拟审校
    head = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys=req_data["keys"], target_lang="ja", variant_key="-"
    )
    assert head is not None
    
    reviewed_rev_id = await coordinator.handler.create_new_translation_revision(
        head_id=head.id, project_id=head.project_id, content_id=head.content_id,
        target_lang="ja", variant_key="-", status=TranslationStatus.REVIEWED,
        revision_no=head.current_no + 1, translated_payload_json={"text": "こんにちは世界"}
    )

    # 1d. 发布
    await status_cmd.publish(ctx=mock_cli_context, revision_id=reviewed_rev_id, actor="test-user")
    assert "已成功发布" in capsys.readouterr().out
    
    # 1e. 获取并验证
    await status_cmd.get_translation(
        ctx=mock_cli_context, project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys_json=json.dumps(req_data["keys"]), target_lang="ja", variant_key="-"
    )
    captured = capsys.readouterr()
    assert "こんにちは世界" in captured.out

    # === 阶段 2: Unpublish (撤回发布) ===

    # 2a. 行动: 通过 CLI 撤回发布
    await status_cmd.unpublish(ctx=mock_cli_context, revision_id=reviewed_rev_id, actor="test-admin")
    assert "发布已被撤回" in capsys.readouterr().out

    # 2b. 验证数据库状态
    async with coordinator._sessionmaker() as session:
        head_after_unpublish = await session.get(ThTransHead, (head.project_id, head.id))
        assert head_after_unpublish is not None
        assert head_after_unpublish.published_rev_id is None, "发布指针应该被清空"
        
        rev_after_unpublish = await session.get(ThTransRev, (head.project_id, reviewed_rev_id))
        assert rev_after_unpublish is not None
        assert rev_after_unpublish.status == TranslationStatus.REVIEWED, "修订状态应回退到 reviewed"

    # === 阶段 3: Reject (拒绝) ===

    # 3a. 行动: 通过 CLI 拒绝现在处于 'reviewed' 状态的修订
    await status_cmd.reject(ctx=mock_cli_context, revision_id=reviewed_rev_id, actor="test-reviewer")
    assert "已被标记为 'rejected'" in capsys.readouterr().out

    # 3b. 验证数据库状态
    async with coordinator._sessionmaker() as session:
        head_after_reject = await session.get(ThTransHead, (head.project_id, head.id))
        assert head_after_reject is not None
        assert head_after_reject.current_status == TranslationStatus.REJECTED, "Head 当前状态应为 rejected"

        rev_after_reject = await session.get(ThTransRev, (head.project_id, reviewed_rev_id))
        assert rev_after_reject is not None
        assert rev_after_reject.status == TranslationStatus.REJECTED, "修订状态应为 rejected"
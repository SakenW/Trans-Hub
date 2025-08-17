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
    测试通过 CLI 驱动的 "Request -> Publish -> Unpublish -> Reject -> Comment" 完整闭环。
    """
    # === 阶段 1 & 2 & 3: Request -> Publish -> Unpublish -> Reject (与之前版本相同) ===
    
    # 1. 准备 & 提交请求
    req_data = create_request_data(target_langs=["ja"], keys={"id": f"cli-e2e-full-{uuid.uuid4().hex[:6]}"})
    await request_cmd.request_new(
        ctx=mock_cli_context, project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys_json=json.dumps(req_data["keys"]), source_payload_json=json.dumps(req_data["source_payload"]),
        target_langs=["ja"],
    )
    assert "翻译请求已成功提交" in capsys.readouterr().out

    # 2. 模拟审校
    head = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys=req_data["keys"], target_lang="ja", variant_key="-"
    )
    assert head is not None
    
    rev_id = await coordinator.handler.create_new_translation_revision(
        head_id=head.id, project_id=head.project_id, content_id=head.content_id,
        target_lang="ja", variant_key="-", status=TranslationStatus.REVIEWED,
        revision_no=head.current_no + 1, translated_payload_json={"text": "こんにちは世界"}
    )

    # 3. 发布
    await status_cmd.publish(ctx=mock_cli_context, revision_id=rev_id)
    assert "已成功发布" in capsys.readouterr().out

    # 4. 撤回发布
    await status_cmd.unpublish(ctx=mock_cli_context, revision_id=rev_id)
    assert "发布已被撤回" in capsys.readouterr().out

    # 5. 拒绝
    await status_cmd.reject(ctx=mock_cli_context, revision_id=rev_id)
    assert "已被标记为 'rejected'" in capsys.readouterr().out

    # === 阶段 4: Commenting (评论) ===

    # 6. 行动: 通过 CLI 添加评论
    comment_author = "cli-test-user"
    comment_body = "This is an E2E test comment."
    await status_cmd.add_comment(
        ctx=mock_cli_context,
        head_id=head.id,
        body=comment_body,
        author=comment_author
    )
    assert "评论已添加" in capsys.readouterr().out

    # 7. 行动: 通过 CLI 查看评论
    await status_cmd.get_comments(ctx=mock_cli_context, head_id=head.id)
    captured = capsys.readouterr()

    # 8. 验证: 断言评论内容和作者存在于 CLI 的输出中
    assert comment_author in captured.out
    assert comment_body in captured.out
    assert "Comments for Head ID" in captured.out
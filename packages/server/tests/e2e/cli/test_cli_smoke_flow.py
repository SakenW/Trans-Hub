# packages/server/tests/e2e/cli/test_cli_smoke_flow.py
"""
对 CLI 进行端到端的冒烟测试。

这个测试模拟了用户从提交请求到获取最终翻译的完整核心流程。
"""
import json
import uuid
import pytest
from unittest.mock import MagicMock

from tests.helpers.factories import create_request_data
from trans_hub.application.coordinator import Coordinator
# 直接导入需要测试的命令函数
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
async def test_cli_translation_request_to_publish_flow(
    coordinator: Coordinator,
    mock_cli_context: MagicMock,
    capsys, # 使用 pytest 内置的 capsys 来捕获 print 输出
):
    """
    测试通过直接调用异步命令函数驱动的 "Request -> Publish -> Get" 完整闭环。
    """
    # --- 1. 准备 ---
    req_data = create_request_data(target_langs=["fr"], keys={"id": f"cli-e2e-{uuid.uuid4().hex[:6]}"})
    
    # --- 2. 行动: 通过直接 await 调用 CLI 命令函数提交翻译请求 ---
    await request_cmd.request_new(
        ctx=mock_cli_context,
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys_json=json.dumps(req_data["keys"]),
        source_payload_json=json.dumps(req_data["source_payload"]),
        target_langs=["fr"],
    )
    captured = capsys.readouterr()
    assert "翻译请求已成功提交" in captured.out

    # --- 3. 幕后操作: 获取新创建的任务，并模拟审校 ---
    head = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"], namespace=req_data["namespace"],
        keys=req_data["keys"], target_lang="fr", variant_key="-"
    )
    assert head is not None and head.current_status == TranslationStatus.DRAFT
    
    reviewed_rev_id = await coordinator.handler.create_new_translation_revision(
        head_id=head.id, project_id=head.project_id, content_id=head.content_id,
        target_lang="fr", variant_key="-", status=TranslationStatus.REVIEWED,
        revision_no=head.current_no + 1, translated_payload_json={"text": "Bonjour le Monde!"}
    )

    # --- 4. 行动: 直接 await 调用 publish 命令 ---
    await status_cmd.publish(ctx=mock_cli_context, revision_id=reviewed_rev_id, actor="test-user")
    captured = capsys.readouterr()
    assert "已成功发布" in captured.out

    # --- 5. 行动: 直接 await 调用 get 命令 ---
    await status_cmd.get_translation(
        ctx=mock_cli_context,
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys_json=json.dumps(req_data["keys"]),
        target_lang="fr",
        variant_key="-"
    )
    captured = capsys.readouterr()
    
    # --- 6. 验证: 直接断言核心内容是否存在于输出中 ---
    assert "Bonjour le Monde!" in captured.out
    assert "已解析的翻译内容" in captured.out
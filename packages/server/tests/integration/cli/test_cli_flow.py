# packages/server/tests/integration/cli/test_cli_flow.py
"""
对 CLI 应用进行端到端的集成测试。(最终版)
"""
import json
from unittest.mock import MagicMock

import pytest
import typer
from typer.testing import CliRunner

from trans_hub.application.coordinator import Coordinator
from trans_hub.presentation.cli._state import CLISharedState
from trans_hub.presentation.cli.commands import request, status
from trans_hub.presentation.cli.main import app
from tests.helpers.factories import create_request_data

runner = CliRunner()


@pytest.fixture
def mock_ctx(coordinator: Coordinator) -> MagicMock:
    """创建一个模拟的 Typer Context，其中包含已初始化的 coordinator。"""
    mock = MagicMock()
    mock.obj = CLISharedState(config=coordinator.config)
    return mock

# 注：db migrate 的测试不再需要，因为它已在 conftest 的 engine fixture 中被隐式覆盖和验证。

@pytest.mark.asyncio
async def test_async_cli_workflow(coordinator: Coordinator, mock_ctx: MagicMock, capsys):
    """
    直接调用异步命令函数进行测试，验证核心工作流。
    """
    # 1. 创建翻译请求
    req_data = create_request_data()
    await request.request_new(
        ctx=mock_ctx,
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys_json=json.dumps(req_data["keys"]),
        source_payload_json=json.dumps(req_data["source_payload"]),
        target_langs=req_data["target_langs"],
    )
    captured = capsys.readouterr()
    assert "✅ 翻译请求已成功提交！" in captured.out

    # 2. (后台操作) 创建一个 'reviewed' 修订
    head = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys=req_data["keys"],
        target_lang=req_data["target_langs"][0],
        variant_key="-",
    )
    assert head is not None
    rev_id = await coordinator.handler.create_new_translation_revision(
        head_id=head.id,
        project_id=head.project_id,
        content_id=head.content_id,
        target_lang=head.target_lang,
        variant_key=head.variant_key,
        status=pytest.importorskip("trans_hub_core.types").TranslationStatus.REVIEWED,
        revision_no=head.current_no + 1,
        translated_payload_json={"text": "Direct Call Test"},
    )

    # 3. 发布修订
    await status.publish(ctx=mock_ctx, revision_id=rev_id)
    captured = capsys.readouterr()
    assert f"✅ 修订 {rev_id} 已成功发布！" in captured.out

    # 4. 获取已发布的翻译
    await status.get_translation(
        ctx=mock_ctx,
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys_json=json.dumps(req_data["keys"]),
        target_lang=req_data["target_langs"][0],
    )
    captured = capsys.readouterr()
    assert "Direct Call Test" in captured.out

@pytest.mark.asyncio
async def test_async_cli_error_handling(mock_ctx: MagicMock):
    """直接调用异步命令函数测试错误处理。"""
    with pytest.raises(typer.Exit) as e:
        await request.request_new(
            ctx=mock_ctx,
            project_id="proj",
            namespace="ns",
            keys_json="{not-json}",
            source_payload_json="{}",
            target_langs=["de"],
        )
    assert e.value.exit_code == 1
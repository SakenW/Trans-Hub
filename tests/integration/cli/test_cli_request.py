# tests/integration/cli/test_cli_request.py
"""测试 UIDA 架构下的 `request new` CLI 命令。"""
import json
from unittest.mock import AsyncMock

from typer.testing import CliRunner

from tests.helpers.factories import TEST_NAMESPACE, TEST_PROJECT_ID
from trans_hub.cli.main import app


def test_request_new_uida_success(
    cli_runner: CliRunner, mock_coordinator: AsyncMock, mock_cli_backend: None
):
    """
    测试 `request new` 命令能否正确解析 UIDA 参数并调用 Coordinator。
    """
    keys = {"view": "home", "id": "title"}
    source_payload = {"text": "Welcome"}
    
    result = cli_runner.invoke(
        app,
        [
            "request",
            "new",
            "--project-id",
            TEST_PROJECT_ID,
            "--namespace",
            TEST_NAMESPACE,
            "--keys-json",
            json.dumps(keys),
            "--source-payload-json",
            json.dumps(source_payload),
            "--source-lang",
            "en",
            "--target",
            "de",
            "--target",
            "fr",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "翻译请求已成功处理" in result.stdout

    # 验证 Coordinator 的 request 方法是否被正确调用
    mock_coordinator.request.assert_awaited_once_with(
        project_id=TEST_PROJECT_ID,
        namespace=TEST_NAMESPACE,
        keys=keys,
        source_payload=source_payload,
        source_lang="en",
        target_langs=["de", "fr"],
    )


def test_request_new_uida_invalid_json_fails(
    cli_runner: CliRunner, mock_coordinator: AsyncMock, mock_cli_backend: None
):
    """测试当提供无效的 JSON 字符串时，命令是否会提前失败。"""
    result = cli_runner.invoke(
        app,
        [
            "request", "new",
            "--project-id", "proj1",
            "--namespace", "ns1",
            "--keys-json", '{"key": "value"', # 无效 JSON
            "--source-payload-json", '{"text": "hi"}',
            "--source-lang", "en",
            "--target", "de",
        ],
    )

    assert result.exit_code == 1
    assert "JSON 格式错误" in result.stdout
    mock_coordinator.request.assert_not_awaited()
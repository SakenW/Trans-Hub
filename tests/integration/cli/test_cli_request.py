# tests/integration/cli/test_cli_request.py
"""
测试 `request` 相关 CLI 命令的集成。
v3.0.0 更新：重写以测试基于业务ID和结构化载荷的新命令接口。
"""

import json
from unittest.mock import ANY, AsyncMock

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from trans_hub.cli.main import app


def test_request_new_calls_async_logic(
    cli_runner: CliRunner, mocker: MockerFixture, mock_cli_backend: None
) -> None:
    """测试 `request new` 命令是否正确调用了其核心异步逻辑。"""
    mock_async_request = mocker.patch(
        "trans_hub.cli.request._async_request_new", new_callable=AsyncMock
    )
    business_id = "test-123"
    payload = {"text": "Hello, world!"}
    payload_str = json.dumps(payload)

    result = cli_runner.invoke(
        app,
        [
            "request",
            "new",
            "--id",
            business_id,
            "--payload-json",
            payload_str,
            "--target",
            "de",
            "--force",
        ],
    )

    assert result.exit_code == 0
    mock_async_request.assert_awaited_once_with(
        ANY, business_id, payload, ["de"], None, True, None
    )


def test_request_new_invalid_lang_code_fails_early(
    cli_runner: CliRunner, mocker: MockerFixture, mock_cli_backend: None
) -> None:
    """测试 `request new` 在提供无效语言代码时失败，且不调用异步逻辑。"""
    mock_async_request = mocker.patch("trans_hub.cli.request._async_request_new")
    result = cli_runner.invoke(
        app,
        [
            "request",
            "new",
            "--id",
            "t-1",
            "--payload-json",
            '{"text":"hi"}',
            "--target",
            "invalid-lang",
        ],
    )
    assert result.exit_code == 1
    assert "语言代码错误" in result.stdout
    mock_async_request.assert_not_called()


def test_request_new_invalid_payload_json_fails_early(
    cli_runner: CliRunner, mocker: MockerFixture, mock_cli_backend: None
) -> None:
    """测试 `request new` 在提供无效 JSON payload 时失败。"""
    mock_async_request = mocker.patch("trans_hub.cli.request._async_request_new")
    result = cli_runner.invoke(
        app,
        [
            "request",
            "new",
            "--id",
            "t-1",
            "--payload-json",
            '{"text":"hi"',  # 格式错误的 JSON
            "--target",
            "de",
        ],
    )
    assert result.exit_code == 1
    assert "Payload 格式错误" in result.stdout
    mock_async_request.assert_not_called()

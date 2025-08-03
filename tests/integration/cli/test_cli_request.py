# tests/integration/cli/test_cli_request.py
"""测试 `request` 相关 CLI 命令的集成。"""

from unittest.mock import ANY, AsyncMock

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from trans_hub.cli.main import app


def test_request_new_calls_async_logic(
    cli_runner: CliRunner, mocker: MockerFixture
) -> None:
    """
    测试 `request new` 命令是否正确调用了其核心异步逻辑。

    v3.1 最终修复：我们直接 mock 目标异步函数 `_async_request_new`。
    """
    mock_async_request = mocker.patch(
        "trans_hub.cli.request._async_request_new", new_callable=AsyncMock
    )
    text = "Hello, world!"
    result = cli_runner.invoke(
        app,
        ["request", "new", text, "--target", "de", "--id", "t-123", "--force"],
    )

    assert result.exit_code == 0
    mock_async_request.assert_awaited_once_with(
        ANY, text, ["de"], None, "t-123", True
    )


def test_request_new_invalid_lang_code_fails_early(
    cli_runner: CliRunner, mocker: MockerFixture
) -> None:
    """测试 `request new` 在提供无效语言代码时失败，且不调用异步逻辑。"""
    mock_async_request = mocker.patch("trans_hub.cli.request._async_request_new")
    result = cli_runner.invoke(
        app, ["request", "new", "text", "--target", "invalid-lang"]
    )
    assert result.exit_code == 1
    assert "语言代码错误" in result.stdout
    mock_async_request.assert_not_called()
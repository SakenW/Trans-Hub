# tests/integration/cli/test_cli_gc.py
"""测试 `gc` 相关 CLI 命令的集成。"""

from unittest.mock import ANY, AsyncMock

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from trans_hub.cli.main import app


def test_gc_run_calls_async_logic(
    cli_runner: CliRunner, mocker: MockerFixture
) -> None:
    """
    测试 `gc run` 命令是否正确调用了其核心异步逻辑。

    v3.1 最终修复：我们不再 mock asyncio.run，而是直接 mock 命令调用的
    目标异步函数 `_async_gc_run`，这更直接地测试了命令的行为。
    """
    mock_async_gc = mocker.patch(
        "trans_hub.cli.gc._async_gc_run", new_callable=AsyncMock
    )
    result = cli_runner.invoke(app, ["gc", "run", "--days", "30", "--yes"])

    assert result.exit_code == 0
    mock_async_gc.assert_awaited_once_with(ANY, 30, True)
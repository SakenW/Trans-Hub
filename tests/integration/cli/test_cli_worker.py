# tests/integration/cli/test_cli_worker.py
# [v2.4] `worker start` CLI 命令测试
"""测试 `worker start` CLI 命令。"""
from unittest.mock import AsyncMock

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from trans_hub.cli.main import app


def test_worker_start_calls_async_logic(
    cli_runner: CliRunner, mocker: MockerFixture
):
    """
    测试 `worker start` 命令能否被成功调用并触发其核心异步逻辑。
    我们不测试循环本身，只确保命令的接线是正确的。
    """
    mock_run_worker_loop = mocker.patch(
        "trans_hub.cli.worker._run_worker_loop", new_callable=AsyncMock
    )
    
    result = cli_runner.invoke(app, ["worker", "start"])
    
    assert result.exit_code == 0, result.stdout
    mock_run_worker_loop.assert_awaited_once()
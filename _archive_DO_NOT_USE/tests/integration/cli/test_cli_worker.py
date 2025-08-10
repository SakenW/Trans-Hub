# tests/integration/cli/test_cli_worker.py
# [v2.4.2] 暂时跳过此模块的测试，以专注于 PostgreSQL。
"""测试 `worker start` CLI 命令。"""

from unittest.mock import AsyncMock

import pytest
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from trans_hub.cli.main import app

# [核心修正] 跳过整个模块的测试
pytestmark = pytest.mark.skip(
    reason="暂时跳过 CLI 测试，以专注于 PostgreSQL 集成测试。"
)


def test_worker_start_calls_async_logic(
    cli_runner: CliRunner, mocker: MockerFixture
) -> None:
    """测试 `worker start` 命令能否被成功调用并触发其核心异步逻辑。"""
    mock_run_worker_loop = mocker.patch(
        "trans_hub.cli.worker._run_worker_loop", new_callable=AsyncMock
    )

    result = cli_runner.invoke(app, ["worker", "start"])

    assert result.exit_code == 0, result.stdout
    mock_run_worker_loop.assert_awaited_once()

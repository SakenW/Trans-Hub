# tests/integration/cli/conftest.py
"""为 CLI 集成测试提供专用的、基于 mock 的 Fixtures。"""
from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from trans_hub.cli.main import app as cli_app
from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator


@pytest.fixture
def cli_runner() -> CliRunner:
    """提供一个 Typer CliRunner 实例用于模拟命令行调用。"""
    return CliRunner()


@pytest.fixture
def mock_cli_config() -> TransHubConfig:
    """提供一个用于 CLI 测试的、可预测的 TransHubConfig mock 实例。"""
    return TransHubConfig(database_url="sqlite+aiosqlite:///:memory:")


@pytest.fixture
def mock_coordinator(mocker: MockerFixture) -> AsyncMock:
    """提供一个 Coordinator 的 AsyncMock 实例，用于隔离测试 CLI 的逻辑。"""
    mock = mocker.create_autospec(Coordinator, instance=True, spec_set=True)
    # 确保核心方法是异步的
    mock.request = AsyncMock()
    mock.initialize = AsyncMock()
    mock.close = AsyncMock()
    mock.publish_translation = AsyncMock()
    mock.reject_translation = AsyncMock()
    mock.get_translation = AsyncMock()
    return mock


@pytest.fixture(autouse=True)
def mock_cli_backend(
    mocker: MockerFixture, mock_cli_config: TransHubConfig, mock_coordinator: AsyncMock
) -> None:
    """自动为所有 CLI 测试修补配置加载和 Coordinator 创建。"""
    # 补丁配置加载
    mocker.patch("trans_hub.cli.main.TransHubConfig", return_value=mock_cli_config)
    # 补丁 Coordinator 的创建
    mocker.patch("trans_hub.cli.utils.create_coordinator", return_value=mock_coordinator)
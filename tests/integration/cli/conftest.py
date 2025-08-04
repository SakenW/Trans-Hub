# tests/integration/cli/conftest.py
# (此文件无需修改，保持原样)
"""为 CLI 集成测试提供专用的、基于 mock 的 Fixtures。"""

from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator


@pytest.fixture
def cli_runner() -> Generator[CliRunner, None, None]:
    """提供一个 Typer CliRunner 实例用于模拟命令行调用。"""
    yield CliRunner()


@pytest.fixture
def mock_cli_config() -> Generator[TransHubConfig, None, None]:
    """提供一个用于 CLI 测试的、可预测的 TransHubConfig mock 实例。"""
    yield TransHubConfig(database_url="sqlite:///cli_test.db")


@pytest.fixture(autouse=True)
def patch_cli_config(mocker: MockerFixture, mock_cli_config: TransHubConfig) -> None:
    """
    自动为所有 CLI 测试修补配置加载。
    """
    mocker.patch("trans_hub.cli.main.TransHubConfig", return_value=mock_cli_config)


@pytest.fixture
def mock_coordinator(mocker: MockerFixture) -> Generator[AsyncMock, None, None]:
    """提供一个 Coordinator 的 AsyncMock 实例，用于隔离测试 CLI 的逻辑。"""
    yield mocker.create_autospec(Coordinator, instance=True, spec_set=True)


@pytest.fixture
def mock_cli_backend(mocker: MockerFixture, mock_coordinator: AsyncMock) -> None:
    """
    修补 CLI 命令的后端依赖（Coordinator 创建和数据库迁移）。
    """
    mocker.patch(
        "trans_hub.cli.utils.create_coordinator", return_value=mock_coordinator
    )
    mocker.patch("trans_hub.cli.db.apply_migrations")
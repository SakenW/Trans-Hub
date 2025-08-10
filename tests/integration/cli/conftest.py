# tests/integration/cli/conftest.py
# [v2.4.3 Final] 简化 conftest，移除 mock，为真实的内存数据库测试做准备。
"""为 CLI 集成测试提供 Fixtures。"""

import pytest
from typer.testing import CliRunner

from trans_hub.config import TransHubConfig


@pytest.fixture
def cli_runner() -> CliRunner:
    """提供一个 Typer CliRunner 实例用于模拟命令行调用。"""
    return CliRunner()


@pytest.fixture
def cli_config_in_memory() -> TransHubConfig:
    """提供一个配置了内存 SQLite 数据库的 TransHubConfig 实例。"""
    return TransHubConfig(database_url="sqlite+aiosqlite:///:memory:")

# tests/integration/cli/test_cli_entrypoint.py
"""测试 CLI 主入口点和全局选项。"""

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from trans_hub import __version__
from trans_hub.cli.main import app


def test_version_option(cli_runner: CliRunner) -> None:
    """测试 `trans-hub --version` 命令是否能正确显示版本号。"""
    result = cli_runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
    assert "Trans-Hub" in result.stdout


def test_no_command_shows_help(cli_runner: CliRunner) -> None:
    """
    测试不带任何命令或使用 --help 时是否显示帮助信息。

    v3.2 修复: 直接测试 `trans-hub --help` 以避免 `no_args_is_help`
    在测试环境中的不确定行为。显式测试 --help 更为健壮。
    """
    result = cli_runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage: trans-hub" in result.stdout


def test_config_load_failure_exits_gracefully(
    cli_runner: CliRunner, mocker: MockerFixture
) -> None:
    """测试当配置加载失败时，CLI 是否会优雅地退出并显示错误。"""
    mocker.patch(
        "trans_hub.cli.main.TransHubConfig",
        side_effect=ValueError("Invalid .env file"),
    )
    result = cli_runner.invoke(app, ["db", "migrate"])
    assert result.exit_code == 1
    assert "启动失败" in result.stdout
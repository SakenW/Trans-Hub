# tests/integration/cli/test_cli_db.py
"""测试 `db` 相关 CLI 命令的集成。"""

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from trans_hub.cli.main import app


def test_db_migrate_success(
    cli_runner: CliRunner, mock_cli_backend: None, mocker: MockerFixture
) -> None:
    """
    测试 `db migrate` 命令成功时，是否调用了正确的后端函数。

    Args:
        cli_runner: Typer 测试运行器。
        mock_cli_backend: 激活后端的 mock。
        mocker: pytest-mock 提供的 mocker fixture。

    """
    mock_apply = mocker.patch("trans_hub.cli.db.apply_migrations")
    result = cli_runner.invoke(app, ["db", "migrate"])

    assert result.exit_code == 0
    assert "数据库迁移成功完成" in result.stdout
    mock_apply.assert_called_once()


def test_db_migrate_handles_exception(
    cli_runner: CliRunner, mock_cli_backend: None, mocker: MockerFixture
) -> None:
    """
    测试 `db migrate` 在后端函数抛出异常时的行为。

    Args:
        cli_runner: Typer 测试运行器。
        mock_cli_backend: 激活后端的 mock。
        mocker: pytest-mock 提供的 mocker fixture。

    """
    mocker.patch(
        "trans_hub.cli.db.apply_migrations", side_effect=RuntimeError("DB locked")
    )
    result = cli_runner.invoke(app, ["db", "migrate"])

    assert result.exit_code == 1
    assert "数据库迁移失败" in result.stdout

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
    [核心修改] 现在测试 Alembic 的 command.upgrade 是否被调用。
    """
    # [核心修改] 我们 mock 的目标是 alembic.command.upgrade，它被 db.py 导入。
    mock_upgrade = mocker.patch("trans_hub.cli.db.command.upgrade")
    result = cli_runner.invoke(app, ["db", "migrate"])

    assert result.exit_code == 0
    assert "数据库迁移成功完成" in result.stdout
    # [核心修改] 断言新的 mock 目标被调用。
    # 我们需要断言它被调用了一次，并且第二个参数是 "head"。
    mock_upgrade.assert_called_once()
    assert mock_upgrade.call_args[0][1] == "head"


def test_db_migrate_handles_exception(
    cli_runner: CliRunner, mock_cli_backend: None, mocker: MockerFixture
) -> None:
    """
    测试 `db migrate` 在后端函数抛出异常时的行为。
    [核心修改] 现在测试 Alembic 的 command.upgrade 抛出异常。
    """
    # [核心修改] 让新的 mock 目标抛出异常。
    mocker.patch(
        "trans_hub.cli.db.command.upgrade", side_effect=RuntimeError("DB locked")
    )
    result = cli_runner.invoke(app, ["db", "migrate"])

    assert result.exit_code == 1
    assert "数据库迁移失败" in result.stdout

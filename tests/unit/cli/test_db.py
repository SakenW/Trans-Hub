# tests/unit/cli/test_db.py
"""
针对 Trans-Hub DB CLI 命令的单元测试。

这些测试验证了 DB 命令的功能，特别是数据库迁移功能和错误处理。
"""

import os
import tempfile
from typing import Generator
from unittest.mock import MagicMock, patch

import pathlib
import sys
import importlib
import types
import pytest
import sqlite3

# 构建临时包以避免执行 trans_hub.__init__
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[3] / "trans_hub"
pkg = types.ModuleType("trans_hub")
pkg.__path__ = [str(PACKAGE_ROOT)]  # type: ignore[attr-defined]
sys.modules["trans_hub"] = pkg

sys.path.append(str(PACKAGE_ROOT.parent))

# 为 trans_hub.utils 提供最小桩，避免加载真实依赖
utils_stub = types.ModuleType("trans_hub.utils")
def _placeholder() -> str:  # pragma: no cover
    return "sqlite:///"
utils_stub.get_database_url = _placeholder  # type: ignore[attr-defined]
sys.modules["trans_hub.utils"] = utils_stub

db_module = importlib.import_module("trans_hub.cli.db.main")
db_migrate = db_module.db_migrate  # type: ignore[attr-defined]


@pytest.fixture
def mock_get_database_url() -> Generator[MagicMock, None, None]:
    """创建一个模拟的 get_database_url 函数。"""
    with patch("trans_hub.cli.db.main.get_database_url") as mock:
        mock.return_value = "sqlite:///:memory:"  # 使用内存数据库进行测试
        yield mock


@pytest.fixture
def temp_db_file() -> Generator[str, None, None]:
    """创建一个临时数据库文件。"""
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        yield tmp_file.name
    os.unlink(tmp_file.name)  # 测试结束后删除临时文件


@patch("trans_hub.cli.db.main.apply_migrations")
@patch("trans_hub.cli.db.main.console.print")
def test_db_migrate_success(
    mock_console_print: MagicMock,
    mock_apply_migrations: MagicMock,
    mock_get_database_url: MagicMock,
) -> None:
    """测试 db_migrate 命令成功执行迁移。"""
    # 调用 db_migrate 命令
    db_migrate()

    # 验证调用
    # 提取数据库路径（去掉 'sqlite:///' 前缀）
    db_url = mock_get_database_url.return_value
    if db_url.startswith("sqlite:///"):
        db_path = db_url[10:]
    elif db_url.startswith("sqlite://"):
        db_path = db_url[9:]
    else:
        db_path = db_url
    mock_apply_migrations.assert_called_once_with(db_path)
    mock_console_print.assert_called()
    assert any("数据库迁移成功完成" in str(call) for call in mock_console_print.call_args_list)


@patch("trans_hub.cli.db.main.apply_migrations")
@patch("trans_hub.cli.db.main.console.print")
def test_db_migrate_file_db(
    mock_console_print: MagicMock,
    mock_apply_migrations: MagicMock,
    mock_get_database_url: MagicMock,
    temp_db_file: str,
) -> None:
    """测试 db_migrate 命令使用文件数据库。"""
    # 配置文件数据库
    mock_get_database_url.return_value = f"sqlite:///{temp_db_file}"

    # 调用 db_migrate 命令
    db_migrate()

    # 验证调用
    # 提取数据库路径（去掉 'sqlite:///' 前缀）
    db_url = mock_get_database_url.return_value
    if db_url.startswith("sqlite:///"):
        db_path = db_url[10:]
    elif db_url.startswith("sqlite://"):
        db_path = db_url[9:]
    else:
        db_path = db_url
    mock_apply_migrations.assert_called_once_with(db_path)
    assert os.path.exists(temp_db_file)  # 确认数据库文件已创建


@patch("trans_hub.cli.db.main.apply_migrations")
@patch("trans_hub.cli.db.main.console.print")
def test_db_migrate_invalid_db_url(
    mock_console_print: MagicMock,
    mock_apply_migrations: MagicMock,
    mock_get_database_url: MagicMock,
) -> None:
    """测试 db_migrate 命令使用无效的数据库 URL。"""
    # 配置无效的数据库 URL
    mock_get_database_url.return_value = "invalid-db-url"

    # 调用 db_migrate 命令，捕获 SystemExit 异常
    with pytest.raises(SystemExit) as excinfo:
        db_migrate()

    # 验证错误处理
    mock_apply_migrations.assert_not_called()
    mock_console_print.assert_called()
    assert any("仅支持 SQLite 数据库的迁移" in str(call) for call in mock_console_print.call_args_list)
    assert excinfo.value.code == 1


@patch("trans_hub.cli.db.main.apply_migrations")
@patch("trans_hub.cli.db.main.console.print")
def test_db_migrate_create_dir(
    mock_console_print: MagicMock,
    mock_apply_migrations: MagicMock,
    mock_get_database_url: MagicMock,
) -> None:
    """测试 db_migrate 命令创建数据库目录。"""
    # 配置带不存在目录的数据库 URL
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "nonexistent", "test.db")
        mock_get_database_url.return_value = f"sqlite:///{db_path}"

        # 调用 db_migrate 命令
        db_migrate()

        # 验证目录已创建
        assert os.path.exists(os.path.dirname(db_path))

    # 验证调用
        # 提取数据库路径（去掉 'sqlite:///' 前缀）
        db_url = mock_get_database_url.return_value
        if db_url.startswith("sqlite:///"):
            db_path = db_url[10:]
        elif db_url.startswith("sqlite://"):
            db_path = db_url[9:]
        else:
            db_path = db_url
        mock_apply_migrations.assert_called_once_with(db_path)


@patch("trans_hub.cli.db.main.apply_migrations")
@patch("trans_hub.cli.db.main.console.print")
def test_db_migrate_migration_error(
    mock_console_print: MagicMock,
    mock_apply_migrations: MagicMock,
    mock_get_database_url: MagicMock,
) -> None:
    """测试 db_migrate 命令在迁移过程中出错。"""
    # 模拟迁移错误
    mock_apply_migrations.side_effect = Exception("Migration error")

    # 调用 db_migrate 命令，捕获 SystemExit 异常
    with pytest.raises(SystemExit) as excinfo:
        db_migrate()

    # 验证错误处理
    mock_apply_migrations.assert_called_once()
    mock_console_print.assert_called()
    assert any("数据库迁移失败" in str(call) for call in mock_console_print.call_args_list)
    assert excinfo.value.code == 1

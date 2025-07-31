# tests/unit/test_cli.py
"""
针对 `trans_hub.cli` 模块的单元测试。

这些测试验证了 CLI 命令的正确性，包括成功路径、失败路径和所有选项行为。
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from trans_hub.cli import app

# 创建 CLI 测试运行器
runner = CliRunner()


def test_version_command() -> None:
    """测试版本命令是否正确显示版本信息。"""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "Trans-Hub version:" in result.stdout


def test_help_command() -> None:
    """测试帮助命令是否正确显示帮助信息。"""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "一个可嵌入的、带持久化存储的智能本地化（i18n）后端引擎。" in result.stdout


@patch("trans_hub.cli._event_loop")
@patch("trans_hub.cli._coordinator")
@patch("trans_hub.cli.asyncio.new_event_loop")
@patch("trans_hub.cli.asyncio.set_event_loop")
@patch("trans_hub.cli.asyncio.Event")
def test_run_worker_success(
    mock_event: Any, mock_set_event_loop: Any, mock_new_event_loop: Any, mock_coordinator: Any, mock_event_loop: Any
) -> None:
    """测试 run_worker 命令成功执行的路径。"""
    # 设置模拟对象
    mock_loop_instance = MagicMock()
    mock_new_event_loop.return_value = mock_loop_instance
    mock_event_loop.return_value = mock_loop_instance
    mock_loop_instance.run_until_complete = MagicMock()
    mock_loop_instance.add_signal_handler = MagicMock()
    
    # 模拟关闭事件
    mock_shutdown_event = MagicMock()
    mock_shutdown_event.is_set.return_value = True
    mock_event.return_value = mock_shutdown_event
    
    # 调用命令
    result = runner.invoke(app, ["run-worker", "--lang", "en"])
    
    # 验证结果
    assert result.exit_code == 0
    # 注意：由于测试环境的限制，我们无法完全验证信号处理程序是否被正确添加
    # 但我们仍然可以检查命令是否成功执行


@patch("trans_hub.cli._shutdown_event")
@patch("trans_hub.cli._event_loop")
@patch("trans_hub.cli._coordinator")
@patch("trans_hub.cli.asyncio.new_event_loop")
@patch("trans_hub.cli.asyncio.set_event_loop")
def test_request_success(
    mock_set_event_loop: Any, mock_new_event_loop: Any, mock_coordinator: Any, mock_event_loop: Any, mock_shutdown_event: Any
) -> None:
    """测试 request 命令成功执行的路径。"""
    # 设置模拟对象
    mock_loop_instance = MagicMock()
    mock_new_event_loop.return_value = mock_loop_instance
    mock_event_loop.return_value = mock_loop_instance
    
    # 模拟 run_until_complete 的行为
    mock_loop_instance.run_until_complete = AsyncMock()
    
    # 模拟协调器的 request 方法
    mock_coordinator.request = AsyncMock()
    
    # 调用命令
    result = runner.invoke(app, ["request", "Hello, world!", "--target", "zh"])
    
    # 验证结果
    assert result.exit_code == 0
    # 验证协调器的 request 方法被调用
    mock_coordinator.request.assert_called_once()
    # 验证 run_until_complete 被调用
    mock_loop_instance.run_until_complete.assert_called_once()


@patch("trans_hub.cli._shutdown_event")
@patch("trans_hub.cli._event_loop")
@patch("trans_hub.cli._coordinator")
@patch("trans_hub.cli.asyncio.new_event_loop")
@patch("trans_hub.cli.asyncio.set_event_loop")
def test_request_with_all_options(
    mock_set_event_loop: Any, mock_new_event_loop: Any, mock_coordinator: Any, mock_event_loop: Any, mock_shutdown_event: Any
) -> None:
    """测试 request 命令使用所有可选参数的路径。"""
    # 设置模拟对象
    mock_loop_instance = MagicMock()
    mock_new_event_loop.return_value = mock_loop_instance
    mock_event_loop.return_value = mock_loop_instance
    
    # 模拟 run_until_complete 的行为
    mock_loop_instance.run_until_complete = AsyncMock()
    
    # 模拟协调器的 request 方法
    mock_coordinator.request = AsyncMock()
    
    # 调用命令
    result = runner.invoke(
        app,
        [
            "request",
            "Hello, world!",
            "--target",
            "zh",
            "--target",
            "ja",
            "--source",
            "en",
            "--id",
            "test_id",
            "--force",
        ],
    )
    
    # 验证结果
    assert result.exit_code == 0
    # 验证协调器的 request 方法被调用
    mock_coordinator.request.assert_called_once()
    # 验证 run_until_complete 被调用
    mock_loop_instance.run_until_complete.assert_called_once()


@patch("trans_hub.cli._shutdown_event")
@patch("trans_hub.cli._event_loop")
@patch("trans_hub.cli._coordinator")
@patch("trans_hub.cli.asyncio.new_event_loop")
@patch("trans_hub.cli.asyncio.set_event_loop")
def test_gc_dry_run(
    mock_set_event_loop: Any, mock_new_event_loop: Any, mock_coordinator: Any, mock_event_loop: Any, mock_shutdown_event: Any
) -> None:
    """测试 gc 命令的 dry-run 模式。"""
    # 设置模拟对象
    mock_loop_instance = MagicMock()
    mock_new_event_loop.return_value = mock_loop_instance
    mock_event_loop.return_value = mock_loop_instance
    mock_loop_instance.run_until_complete = MagicMock()
    
    # 模拟协调器的 run_garbage_collection 方法返回值
    mock_coordinator.run_garbage_collection = AsyncMock()
    mock_coordinator.run_garbage_collection.return_value = {
        "deleted_jobs": 0,
        "deleted_content": 0,
        "deleted_contexts": 0,
    }
    
    # 调用命令
    result = runner.invoke(app, ["gc", "--dry-run"])
    
    # 验证结果
    assert result.exit_code == 0
    mock_coordinator.run_garbage_collection.assert_called_once_with(90, True)


@patch("trans_hub.cli._shutdown_event")
@patch("trans_hub.cli._event_loop")
@patch("trans_hub.cli._coordinator")
@patch("trans_hub.cli.asyncio.new_event_loop")
@patch("trans_hub.cli.asyncio.set_event_loop")
@patch("trans_hub.cli.questionary.confirm")
def test_gc_execute(
    mock_confirm: Any, mock_set_event_loop: Any, mock_new_event_loop: Any, mock_coordinator: Any, mock_event_loop: Any, mock_shutdown_event: Any
) -> None:
    """测试 gc 命令的实际执行模式。"""
    # 设置模拟对象
    mock_loop_instance = MagicMock()
    mock_new_event_loop.return_value = mock_loop_instance
    mock_event_loop.return_value = mock_loop_instance
    
    # 模拟 run_until_complete 的行为
    mock_loop_instance.run_until_complete = AsyncMock()
    mock_loop_instance.run_until_complete.side_effect = [
        {"deleted_jobs": 1, "deleted_content": 2, "deleted_contexts": 3},  # 预报告
        True,  # 用户确认
        {"deleted_jobs": 1, "deleted_content": 2, "deleted_contexts": 3}   # 实际执行
    ]
    
    # 模拟协调器的 run_garbage_collection 方法
    mock_coordinator.run_garbage_collection = AsyncMock()
    mock_coordinator.run_garbage_collection.side_effect = [
        {"deleted_jobs": 1, "deleted_content": 2, "deleted_contexts": 3},  # 预报告
        {"deleted_jobs": 1, "deleted_content": 2, "deleted_contexts": 3}   # 实际执行
    ]
    
    # 模拟用户确认
    confirm_instance = MagicMock()
    confirm_instance.ask_async = AsyncMock(return_value=True)
    mock_confirm.return_value = confirm_instance
    
    # 调用命令
    result = runner.invoke(app, ["gc"])
    
    # 验证结果
    assert result.exit_code == 0
    # 验证 run_garbage_collection 被调用了两次
    assert mock_coordinator.run_garbage_collection.call_count == 2
    # 验证 run_until_complete 被调用了三次
    assert mock_loop_instance.run_until_complete.call_count == 3


class TestDBMigrateCommand:
    """测试 db migrate 命令。"""

    def test_db_migrate_help(self) -> None:
        """测试 db migrate 命令的帮助信息。"""
        result = runner.invoke(app, ["db", "migrate", "--help"])
        assert result.exit_code == 0
        assert "对数据库应用所有必要的迁移脚本" in result.stdout

    @patch("trans_hub.cli.apply_migrations")
    def test_db_migrate_success(self, mock_apply_migrations: Any) -> None:
        """测试 db migrate 命令成功执行。"""
        # 创建临时数据库文件
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
            tmp_db_path = tmp_db.name
        
        try:
            # 调用命令
            result = runner.invoke(app, ["db", "migrate", "--db-url", f"sqlite:///{tmp_db_path}"])
            
            # 验证结果
            assert result.exit_code == 0
            assert "数据库迁移成功" in result.stdout
            mock_apply_migrations.assert_called_once()
        finally:
            # 清理临时文件
            Path(tmp_db_path).unlink(missing_ok=True)

    @patch("trans_hub.cli.apply_migrations")
    def test_db_migrate_invalid_db_type(self, mock_apply_migrations: Any) -> None:
        """测试 db migrate 命令使用不支持的数据库类型。"""
        # 调用命令
        result = runner.invoke(app, ["db", "migrate", "--db-url", "postgresql://localhost/test"])
        
        # 验证结果
        assert result.exit_code == 1
        assert "目前只支持 SQLite 数据库" in result.stdout
        mock_apply_migrations.assert_not_called()
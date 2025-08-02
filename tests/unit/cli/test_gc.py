# tests/unit/cli/test_gc.py
"""
针对 Trans-Hub GC CLI 命令的单元测试。

这些测试验证了 GC 命令的功能，包括垃圾回收报告生成、干运行模式和用户交互。
"""

import asyncio
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import questionary

from trans_hub.cli.gc.main import gc
from trans_hub.coordinator import Coordinator


@pytest.fixture
def mock_coordinator() -> MagicMock:
    """创建一个模拟的协调器对象。"""
    coordinator = MagicMock(spec=Coordinator)
    coordinator.run_garbage_collection = AsyncMock()
    return coordinator


@pytest.fixture
def mock_event_loop() -> MagicMock:
    """创建一个模拟的事件循环对象。"""
    loop = MagicMock(spec=asyncio.AbstractEventLoop)
    # 模拟run_until_complete，确保它返回协程的结果
    loop.run_until_complete = MagicMock(side_effect=lambda coro: asyncio.run(coro) if asyncio.iscoroutine(coro) else coro)
    return loop


@pytest.fixture
def mock_questionary_confirm() -> Generator[MagicMock, None, None]:
    """创建一个模拟的 questionary.confirm 函数。"""
    with patch("questionary.confirm") as mock:
        yield mock


@patch("trans_hub.cli.gc.main.console.print")
def test_gc_dry_run(
    mock_console_print: MagicMock,
    mock_coordinator: MagicMock,
    mock_event_loop: MagicMock,
) -> None:
    """测试 gc 命令的干运行模式。"""
    # 准备测试数据
    retention_days = 90
    dry_run = True

    # 模拟垃圾回收报告
    mock_report = {"deleted_jobs": 5, "deleted_content": 10, "deleted_contexts": 3}
    mock_coordinator.run_garbage_collection.return_value = mock_report

    # 调用 gc 命令
    gc(mock_coordinator, mock_event_loop, retention_days, dry_run)

    # 验证调用
    mock_coordinator.run_garbage_collection.assert_called_once_with(
        retention_days, True
    )
    mock_event_loop.run_until_complete.assert_called_once()
    mock_console_print.assert_called()

    # 验证没有执行实际删除
    assert mock_coordinator.run_garbage_collection.call_count == 1


@patch("trans_hub.cli.gc.main.console.print")
def test_gc_real_run_confirmed(
    mock_console_print: MagicMock,
    mock_coordinator: MagicMock,
    mock_event_loop: MagicMock,
    mock_questionary_confirm: MagicMock,
) -> None:
    """测试 gc 命令的实际运行模式（用户确认）。"""
    # 准备测试数据
    retention_days = 90
    dry_run = False

    # 模拟垃圾回收报告
    mock_report = {"deleted_jobs": 5, "deleted_content": 10, "deleted_contexts": 3}
    mock_coordinator.run_garbage_collection.return_value = mock_report

    # 模拟用户确认
    mock_questionary_confirm.return_value.ask_async.return_value = True

    # 调用 gc 命令
    gc(mock_coordinator, mock_event_loop, retention_days, dry_run)

    # 输出调试信息
    print(f"run_garbage_collection 调用次数: {mock_coordinator.run_garbage_collection.call_count}")
    print(f"run_until_complete 调用次数: {mock_event_loop.run_until_complete.call_count}")
    print(f"questionary.confirm 调用次数: {mock_questionary_confirm.call_count}")
    print(f"run_until_complete 调用参数: {[call[0][0] for call in mock_event_loop.run_until_complete.call_args_list]}")

    # 验证调用
    # 在实际代码中，无论是否dry_run，都会先调用run_garbage_collection(True)生成预报告
    # 当dry_run=False且用户确认时，会再次调用run_garbage_collection(False)执行删除
    assert mock_coordinator.run_garbage_collection.call_count == 2, f"预期调用2次，实际调用{mock_coordinator.run_garbage_collection.call_count}次"
    mock_coordinator.run_garbage_collection.assert_any_call(retention_days, True)
    mock_coordinator.run_garbage_collection.assert_any_call(retention_days, False)
    # 确保 run_until_complete 被调用了至少三次（一次用于预报告，一次用于questionary.confirm，一次用于实际删除）
    assert mock_event_loop.run_until_complete.call_count >= 3, f"预期至少调用3次，实际调用{mock_event_loop.run_until_complete.call_count}次"
    mock_questionary_confirm.assert_called_once()


@patch("trans_hub.cli.gc.main.console.print")
def test_gc_real_run_cancelled(
    mock_console_print: MagicMock,
    mock_coordinator: MagicMock,
    mock_event_loop: MagicMock,
    mock_questionary_confirm: MagicMock,
) -> None:
    """测试 gc 命令的实际运行模式（用户取消）。"""
    # 准备测试数据
    retention_days = 90
    dry_run = False

    # 模拟垃圾回收报告
    mock_report = {"deleted_jobs": 5, "deleted_content": 10, "deleted_contexts": 3}
    mock_coordinator.run_garbage_collection.return_value = mock_report

    # 模拟用户取消
    mock_questionary_confirm.return_value.ask_async.return_value = False

    # 调用 gc 命令
    gc(mock_coordinator, mock_event_loop, retention_days, dry_run)

    # 输出调试信息
    print(f"run_garbage_collection 调用次数: {mock_coordinator.run_garbage_collection.call_count}")
    print(f"run_until_complete 调用次数: {mock_event_loop.run_until_complete.call_count}")
    print(f"questionary.confirm 调用次数: {mock_questionary_confirm.call_count}")
    print(f"run_until_complete 调用参数: {[call[0][0] for call in mock_event_loop.run_until_complete.call_args_list]}")

    # 验证调用
    # 在实际代码中，无论用户是否确认，都会先调用run_garbage_collection(True)生成预报告
    assert mock_coordinator.run_garbage_collection.call_count == 1, f"预期调用1次，实际调用{mock_coordinator.run_garbage_collection.call_count}次"
    mock_coordinator.run_garbage_collection.assert_called_once_with(
        retention_days, True
    )
    # 确保 run_until_complete 被调用了至少两次（一次用于预报告，一次用于questionary.confirm）
    assert mock_event_loop.run_until_complete.call_count >= 2, f"预期至少调用2次，实际调用{mock_event_loop.run_until_complete.call_count}次"
    mock_questionary_confirm.assert_called_once()


@patch("trans_hub.cli.gc.main.console.print")
def test_gc_no_data_to_clean(
    mock_console_print: MagicMock,
    mock_coordinator: MagicMock,
    mock_event_loop: MagicMock,
) -> None:
    """测试 gc 命令在没有数据可清理时的行为。"""
    # 准备测试数据
    retention_days = 90
    dry_run = False

    # 模拟空垃圾回收报告
    mock_report = {"deleted_jobs": 0, "deleted_content": 0, "deleted_contexts": 0}
    mock_coordinator.run_garbage_collection.return_value = mock_report

    # 调用 gc 命令
    gc(mock_coordinator, mock_event_loop, retention_days, dry_run)

    # 验证调用
    mock_coordinator.run_garbage_collection.assert_called_once_with(
        retention_days, True
    )
    # 验证没有显示确认对话框
    assert "数据库很干净，无需进行垃圾回收" in str(mock_console_print.call_args_list)

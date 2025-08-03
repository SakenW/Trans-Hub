# tests/unit/cli/test_worker.py
"""精简的 Worker CLI 测试。

该测试确保 ``run_worker`` 在基础环境中能够被调用，并正确
注册信号处理器以及触发事件循环的执行。为避免引入真实依赖，
此文件使用占位类和大量的 `MagicMock`。
"""

from __future__ import annotations

import asyncio
import importlib
import pathlib
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

# 构建临时包以避免执行 trans_hub.__init__
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[3] / "trans_hub"
pkg = types.ModuleType("trans_hub")
pkg.__path__ = [str(PACKAGE_ROOT)]  # type: ignore[attr-defined]
sys.modules["trans_hub"] = pkg
sys.path.append(str(PACKAGE_ROOT.parent))

worker_module = importlib.import_module("trans_hub.cli.worker.main")
run_worker = worker_module.run_worker  # type: ignore[attr-defined]


class Coordinator:  # pragma: no cover - 占位类型
    async def process_pending_translations(self, *args, **kwargs):
        pass

    async def close(self):
        pass


def test_run_worker_basic() -> None:
    """调用 ``run_worker`` 时应注册信号处理器并尝试关闭协调器。"""

    coordinator = MagicMock(spec=Coordinator)
    coordinator.process_pending_translations.return_value = []
    coordinator.close = AsyncMock()

    loop = MagicMock()
    loop.add_signal_handler = MagicMock()
    loop.run_until_complete = MagicMock()

    shutdown_event = asyncio.Event()

    # 避免实际的异步调度
    with patch.object(worker_module.asyncio, "gather", return_value=[]), \
         patch.object(worker_module.asyncio, "all_tasks", return_value=set()), \
         patch.object(worker_module.asyncio, "current_task", return_value=None), \
         patch.object(worker_module.asyncio, "create_task", side_effect=lambda coro: (coro.close() or MagicMock())):
        run_worker(coordinator, loop, shutdown_event, ["en"])

    assert loop.add_signal_handler.call_count >= 2
    assert loop.run_until_complete.call_count >= 1


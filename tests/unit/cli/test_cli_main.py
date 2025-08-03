# tests/unit/cli/test_cli_main.py
"""针对 Trans‑Hub CLI 主入口的单元测试。

这些测试在没有真实 Typer 依赖的情况下验证 CLI 主逻辑。为了
简化依赖，我们直接调用回调函数并使用简单的 MagicMock 对象来
模拟上下文。
"""

import pathlib
import sys
from unittest.mock import MagicMock, patch
import importlib.util
import types

import pytest

# 构建一个无需执行 ``trans_hub.__init__`` 的临时包，从而避免昂贵的依赖。
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[3] / "trans_hub"
pkg = types.ModuleType("trans_hub")
pkg.__path__ = [str(PACKAGE_ROOT)]  # type: ignore[attr-defined]
sys.modules["trans_hub"] = pkg

# 允许导入同目录下提供的依赖桩
sys.path.append(str(PACKAGE_ROOT.parent))

spec = importlib.util.spec_from_file_location("trans_hub.cli", PACKAGE_ROOT / "cli" / "__init__.py")
cli = importlib.util.module_from_spec(spec)
sys.modules["trans_hub.cli"] = cli
spec.loader.exec_module(cli)  # type: ignore[union-attr]

from trans_hub.cli import app, gc, main, request, worker  # type: ignore[attr-defined]


@pytest.mark.parametrize("version_flag", [True, False])
def test_main_command(version_flag: bool, capsys: pytest.CaptureFixture[str]) -> None:
    """测试 main 回调的版本输出和帮助调用。"""

    ctx = MagicMock()
    ctx.invoked_subcommand = None
    ctx.get_help.return_value = "help"

    with pytest.raises(SystemExit) as exc:
        main(ctx, version=version_flag)

    # 无论是否传入 --version，退出码都应为 0
    assert exc.value.code == 0 or exc.value.code is None

    captured = capsys.readouterr().out
    if version_flag:
        assert "Version" in captured and "1.0.0" in captured
    else:
        ctx.get_help.assert_called_once()


def test_command_decorator_applied() -> None:
    """CLI 应用应具备 command 方法以注册子命令。"""

    assert hasattr(app, "command")


def test_cli_app_structure() -> None:
    """CLI 应用应当已经注册了一些命令。"""

    assert hasattr(app, "registered_commands")
    assert len(app.registered_commands) > 0


@pytest.mark.parametrize("command_func", [worker, request, gc])
def test_command_requires_coordinator(command_func) -> None:
    """当协调器初始化失败时，命令应抛出 SystemExit。"""

    with patch("trans_hub.cli._initialize_coordinator", side_effect=RuntimeError("fail")):
        with pytest.raises(SystemExit):
            command_func()  # type: ignore[arg-type]


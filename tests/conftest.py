# tests/conftest.py
"""项目全局共享的测试 Fixtures。"""

from collections.abc import Generator
from typing import Any

import pytest
from pytest_mock import MockerFixture
from rich.console import Console


@pytest.fixture(scope="session", autouse=True)
def disable_rich_colors_for_tests(
    session_mocker: MockerFixture,
) -> Generator[None, None, None]:
    """
    全局禁用 rich 库的颜色输出，以确保测试结果的确定性。

    此 fixture 使用 `session` 作用域和 `autouse=True`，将自动应用于整个测试会话。
    它通过修补 `rich.console.Console` 的构造函数，强制其在测试期间
    表现得像一个不支持颜色的终端。

    Args:
        session_mocker: pytest-mock 提供的会话作用域 mocker。
    """
    original_init = Console.__init__

    def new_init(self: Console, *args: Any, **kwargs: Any) -> None:
        kwargs["force_terminal"] = False
        kwargs["color_system"] = None
        original_init(self, *args, **kwargs)

    # v3.1 最终修复：移除 autospec=True 参数。
    # 当手动提供 `new` 对象时，不能同时使用 `autospec`。
    session_mocker.patch("rich.console.Console.__init__", new=new_init)
    yield
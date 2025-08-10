# tests/conftest.py
# (此文件保持不变，因为它处理的是与 rich 库相关的全局配置)
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
    """全局禁用 rich 库的颜色输出，以确保测试结果的确定性。"""
    original_init = Console.__init__

    def new_init(self: Console, *args: Any, **kwargs: Any) -> None:
        kwargs["force_terminal"] = False
        kwargs["color_system"] = None
        original_init(self, *args, **kwargs)

    session_mocker.patch("rich.console.Console.__init__", new=new_init)
    yield

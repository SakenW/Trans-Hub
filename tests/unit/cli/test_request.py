# tests/unit/cli/test_request.py
"""
针对 Trans-Hub Request CLI 命令的单元测试。

这些测试验证了 Request 命令的功能，包括参数解析、翻译请求提交和错误处理。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pathlib
import sys
import importlib
import types
import pytest

# 构建临时包以避免执行 trans_hub.__init__
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[3] / "trans_hub"
pkg = types.ModuleType("trans_hub")
pkg.__path__ = [str(PACKAGE_ROOT)]  # type: ignore[attr-defined]
sys.modules["trans_hub"] = pkg

sys.path.append(str(PACKAGE_ROOT.parent))

request_module = importlib.import_module("trans_hub.cli.request.main")
_async_request = request_module._async_request  # type: ignore[attr-defined]
request = request_module.request  # type: ignore[attr-defined]

import enum

class Coordinator:  # pragma: no cover - placeholder
    pass

class TranslationResult:  # pragma: no cover - placeholder
    pass

class TranslationStatus(enum.Enum):  # pragma: no cover
    PENDING = "pending"
    TRANSLATED = "translated"


@pytest.fixture
def mock_coordinator() -> MagicMock:
    """创建一个模拟的协调器对象。"""
    coordinator = MagicMock(spec=Coordinator)
    coordinator.request = AsyncMock()
    coordinator.close = AsyncMock()
    return coordinator


@pytest.fixture
def mock_event_loop() -> MagicMock:
    """创建一个模拟的事件循环对象。"""
    loop = MagicMock(spec=asyncio.AbstractEventLoop)
    loop.run_until_complete = MagicMock()
    return loop


def test_async_request_success(mock_coordinator: MagicMock) -> None:
    """测试 _async_request 函数成功提交翻译请求。"""
    # 准备测试数据
    text = "Hello, world!"
    target_lang = "zh-CN"
    source_lang = "en"
    context_id = "ctx-123"
    priority = 1

    # 模拟 submit_translation 返回结果
    mock_result = MagicMock(spec=TranslationResult)
    mock_result.id = "req-123"
    mock_result.status = TranslationStatus.PENDING
    mock_coordinator.request.return_value = mock_result

    # 调用 _async_request
    asyncio.run(
        _async_request(
            mock_coordinator, text, [target_lang], source_lang, context_id, priority > 0
        )
    )

    # 验证调用
    mock_coordinator.request.assert_called_once_with(
        text_content=text,
        target_langs=[target_lang],
        source_lang=source_lang,
        business_id=context_id,
        force_retranslate=True,
    )


def test_async_request_missing_source_lang(mock_coordinator: MagicMock) -> None:
    """测试 _async_request 函数在缺少源语言时的行为。"""
    # 准备测试数据
    text = "Hello, world!"
    target_lang = "zh-CN"
    source_lang = None
    context_id = None
    priority = 0

    # 模拟 submit_translation 返回结果
    mock_result = MagicMock(spec=TranslationResult)
    mock_coordinator.request.return_value = mock_result

    # 调用 _async_request
    asyncio.run(
        _async_request(
            mock_coordinator, text, [target_lang], source_lang, context_id, priority > 0
        )
    )

    # 验证源语言被设为 auto
    # 使用call_args_list来检查调用参数
    assert mock_coordinator.request.call_count == 1
    call_args = mock_coordinator.request.call_args_list[0][1]
    assert call_args["source_lang"] is None
    assert call_args["text_content"] == text
    assert call_args["target_langs"] == [target_lang]
    assert call_args["business_id"] == context_id
    assert call_args["force_retranslate"] == priority


def test_request_success(
    mock_coordinator: MagicMock,
) -> None:
    """测试 request 函数成功提交翻译请求。"""
    # 准备测试数据
    text = "Hello, world!"
    target_lang = ["zh-CN"]
    source_lang = "en"
    business_id = "ctx-123"
    force = True

    # 模拟 request 返回结果
    mock_result = MagicMock(spec=TranslationResult)
    mock_coordinator.request.return_value = mock_result

    # 直接测试 _async_request 协程
    asyncio.run(
        _async_request(
            mock_coordinator,
            text,
            target_lang,
            source_lang,
            business_id,
            force,
        )
    )

    # 验证调用
    mock_coordinator.request.assert_called_once_with(
        text_content=text,
        target_langs=target_lang,
        source_lang=source_lang,
        business_id=business_id,
        force_retranslate=force,
    )


@patch("asyncio.new_event_loop")
def test_request_error_handling(
    mock_new_event_loop: MagicMock,
    mock_coordinator: MagicMock,
) -> None:
    """测试 request 函数的错误处理。"""
    # 准备测试数据
    text = "Hello, world!"
    target_lang = ["zh-CN"]
    source_lang = None
    business_id = None
    force = False

    # 配置模拟: 让 request 方法抛出异常
    mock_coordinator.request.side_effect = Exception("Request error")

    # 直接测试 _async_request 协程
    with pytest.raises(Exception, match="Request error"):
        asyncio.run(
            _async_request(
                mock_coordinator,
                text,
                target_lang,
                source_lang,
                business_id,
                force,
            )
        )

    # 验证请求被调用
    mock_coordinator.request.assert_called_once_with(
        text_content=text,
        target_langs=target_lang,
        source_lang=source_lang,
        business_id=business_id,
        force_retranslate=force,
    )

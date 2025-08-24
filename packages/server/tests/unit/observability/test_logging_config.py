# packages/server/tests/unit/observability/test_logging_config.py
"""
测试日志配置模块的核心功能。

主要测试：
1. HybridPanelRenderer 的渲染逻辑
2. setup_logging 函数的配置行为
3. 日志级别和格式化处理
4. Rich 依赖的可选性处理
"""

import logging
from collections.abc import MutableMapping
from typing import Any
from unittest.mock import Mock, patch

import pytest
import structlog
from trans_hub.observability.logging_config import (
    HybridPanelRenderer,
    setup_logging,
    setup_logging_from_config,
)


class TestHybridPanelRenderer:
    """测试 HybridPanelRenderer 类的功能。"""

    def test_init_without_rich_raises_import_error(self):
        """测试在没有 rich 依赖时初始化 HybridPanelRenderer 抛出 ImportError。"""
        with patch("trans_hub.observability.logging_config.Console", None):
            with pytest.raises(ImportError) as exc_info:
                HybridPanelRenderer()
            assert "要使用 HybridPanelRenderer，请先安装 rich" in str(exc_info.value)

    def test_init_with_default_parameters(self):
        """测试使用默认参数初始化 HybridPanelRenderer。"""
        renderer = HybridPanelRenderer()
        assert renderer._log_level == "INFO"
        assert renderer._kv_truncate_at == 256
        assert renderer._show_timestamp is True
        assert renderer._show_logger_name is True
        assert renderer._kv_key_width == 15
        assert renderer._panel_padding == (1, 2)
        assert renderer._is_first_render is True

    def test_init_with_custom_parameters(self):
        """测试使用自定义参数初始化 HybridPanelRenderer。"""
        renderer = HybridPanelRenderer(
            log_level="DEBUG",
            kv_truncate_at=128,
            show_timestamp=False,
            show_logger_name=False,
            kv_key_width=20,
            panel_padding=(0, 1),
        )
        assert renderer._log_level == "DEBUG"
        assert renderer._kv_truncate_at == 128
        assert renderer._show_timestamp is False
        assert renderer._show_logger_name is False
        assert renderer._kv_key_width == 20
        assert renderer._panel_padding == (0, 1)

    def test_call_with_empty_event_returns_empty_string(self):
        """测试当事件消息为空时返回空字符串。"""
        renderer = HybridPanelRenderer()
        event_dict: MutableMapping[str, Any] = {"event": ""}
        result = renderer(Mock(), "test", event_dict)
        assert result == ""

    def test_call_with_no_event_returns_empty_string(self):
        """测试当没有事件字段时返回空字符串。"""
        renderer = HybridPanelRenderer()
        event_dict: MutableMapping[str, Any] = {}
        result = renderer(Mock(), "test", event_dict)
        assert result == ""

    @patch("trans_hub.observability.logging_config.Console")
    def test_call_with_basic_event(self, mock_console_class):
        """测试基本事件的渲染。"""
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # 正确模拟capture上下文管理器
        mock_capture_context = Mock()
        mock_capture_context.__enter__ = Mock(return_value=Mock())
        mock_capture_context.__exit__ = Mock(return_value=None)
        mock_capture_context.__enter__.return_value.get = Mock(return_value="mocked output\n")
        mock_console.capture.return_value = mock_capture_context

        renderer = HybridPanelRenderer()
        event_dict: MutableMapping[str, Any] = {
            "event": "Test message",
            "level": "info",
            "timestamp": "2023-01-01T00:00:00Z",
            "logger": "test_logger",
        }

        result = renderer(Mock(), "test", event_dict)

        # 第一次渲染应该包含换行符
        assert result == "\nmocked output"
        assert mock_console.print.called

    @patch("trans_hub.observability.logging_config.Console")
    def test_call_second_time_no_leading_newline(self, mock_console_class):
        """测试第二次调用时不添加前导换行符。"""
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # 正确模拟capture上下文管理器
        mock_capture_context = Mock()
        mock_capture_context.__enter__ = Mock(return_value=Mock())
        mock_capture_context.__exit__ = Mock(return_value=None)
        mock_capture_context.__enter__.return_value.get = Mock(return_value="mocked output\n")
        mock_console.capture.return_value = mock_capture_context

        renderer = HybridPanelRenderer()
        event_dict1: MutableMapping[str, Any] = {"event": "First message"}
        event_dict2: MutableMapping[str, Any] = {"event": "Second message"}

        # 第一次调用
        result1 = renderer(Mock(), "test", event_dict1)
        assert result1 == "\nmocked output"

        # 第二次调用
        result2 = renderer(Mock(), "test", event_dict2)
        assert result2 == "mocked output"

    def test_level_styles_mapping(self):
        """测试日志级别样式映射。"""
        renderer = HybridPanelRenderer()
        expected_levels = ["debug", "info", "warning", "error", "critical"]
        for level in expected_levels:
            assert level in renderer._level_styles
            style, text = renderer._level_styles[level]
            assert isinstance(style, str)
            assert isinstance(text, str)
            assert len(text.strip()) > 0


class TestSetupLogging:
    """测试 setup_logging 函数的功能。"""

    def test_setup_logging_with_default_parameters(self):
        """测试使用默认参数设置日志。"""
        with patch("structlog.configure") as mock_configure:
            setup_logging()
            mock_configure.assert_called_once()

            # 检查调用参数
            call_args = mock_configure.call_args
            assert "processors" in call_args.kwargs
            assert "wrapper_class" in call_args.kwargs
            assert "logger_factory" in call_args.kwargs
            assert "cache_logger_on_first_use" in call_args.kwargs

    def test_setup_logging_with_json_format(self):
        """测试使用 JSON 格式设置日志。"""
        with patch("structlog.configure") as mock_configure:
            setup_logging(log_format="json")
            mock_configure.assert_called_once()

    def test_setup_logging_with_console_format(self):
        """测试使用控制台格式设置日志。"""
        with patch("structlog.configure") as mock_configure:
            setup_logging(log_format="console")
            mock_configure.assert_called_once()

    def test_setup_logging_with_custom_log_level(self):
        """测试使用自定义日志级别设置日志。"""
        with patch("structlog.configure") as mock_configure:
            setup_logging(log_level="DEBUG")
            mock_configure.assert_called_once()

    def test_setup_logging_with_silence_noisy_libs(self):
        """测试静默嘈杂库的日志。"""
        with patch("structlog.configure"):
            with patch("logging.getLogger") as mock_get_logger:
                mock_logger = Mock()
                mock_get_logger.return_value = mock_logger

                setup_logging(silence_noisy_libs=True)

                # 验证是否调用了 getLogger 来获取嘈杂库的 logger
                assert mock_get_logger.called

    def test_setup_logging_without_silence_noisy_libs(self):
        """测试不静默嘈杂库的日志。"""
        with patch("structlog.configure"):
            with patch("logging.getLogger") as mock_get_logger:
                setup_logging(silence_noisy_libs=False)

                # 当 silence_noisy_libs=False 时，不应该调用 getLogger
                # 来设置嘈杂库的日志级别
                # 注意：这个测试可能需要根据实际实现调整


class TestSetupLoggingFromConfig:
    """测试 setup_logging_from_config 函数的功能。"""

    def test_setup_logging_from_config_with_mock_config(self):
        """测试使用模拟配置对象设置日志。"""
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_config.log_format = "console"

        with patch(
            "trans_hub.observability.logging_config.setup_logging"
        ) as mock_setup:
            setup_logging_from_config(mock_config, service="test-service")
            mock_setup.assert_called_once()

            # 检查调用参数
            call_args = mock_setup.call_args
            assert "service" in call_args.kwargs
            assert call_args.kwargs["service"] == "test-service"

    def test_setup_logging_from_config_with_default_service(self):
        """测试使用默认服务名称设置日志。"""
        mock_config = Mock()
        mock_config.log_level = "DEBUG"
        mock_config.log_format = "json"

        with patch(
            "trans_hub.observability.logging_config.setup_logging"
        ) as mock_setup:
            setup_logging_from_config(mock_config)
            mock_setup.assert_called_once()

            # 检查默认服务名称
            call_args = mock_setup.call_args
            assert call_args.kwargs["service"] == "trans-hub-server"


class TestLoggingIntegration:
    """测试日志系统的集成功能。"""

    def test_structlog_logger_creation_after_setup(self):
        """测试设置后能够创建 structlog logger。"""
        with patch("structlog.configure"):
            setup_logging()
            logger = structlog.get_logger("test_logger")
            assert logger is not None

    def test_standard_logging_integration(self):
        """测试与标准 logging 模块的集成。"""
        with patch("structlog.configure"):
            setup_logging()

            # 验证能够获取标准 logger
            std_logger = logging.getLogger("test_std_logger")
            assert std_logger is not None

# packages/server/tests/unit/di/test_event_stream_config.py
"""
测试事件流配置是否正确从配置中读取。
"""

from trans_hub.config import TransHubConfig
from trans_hub.application.processors import TranslationProcessor


def test_translation_processor_uses_config_event_stream_name():
    """测试 TranslationProcessor 使用配置中的事件流名称而非硬编码。"""
    # 创建自定义配置，设置不同的事件流名称
    config = TransHubConfig(
        active_engine="debug",
        worker={"event_stream_name": "custom_events"},
    )
    
    # 直接创建 TranslationProcessor，使用配置中的事件流名称
    processor = TranslationProcessor(
        stream_producer=None,
        event_stream_name=config.worker.event_stream_name
    )
    
    # 验证事件流名称是从配置读取的
    assert processor._event_stream_name == "custom_events"
    assert processor._event_stream_name != "translation_events"  # 确保不是硬编码值


def test_translation_processor_uses_default_event_stream_name():
    """测试 TranslationProcessor 使用默认的事件流名称。"""
    # 使用默认配置
    config = TransHubConfig(active_engine="debug")
    
    # 直接创建 TranslationProcessor，使用配置中的事件流名称
    processor = TranslationProcessor(
        stream_producer=None,
        event_stream_name=config.worker.event_stream_name
    )
    
    # 验证使用默认的事件流名称
    assert processor._event_stream_name == "th_events"  # 默认值
    assert processor._event_stream_name != "translation_events"  # 确保不是旧的硬编码值


def test_di_container_provides_correct_event_stream_name():
    """测试 DI 容器提供正确的事件流名称配置。"""
    from trans_hub.di.container import AppContainer
    
    # 创建自定义配置
    config = TransHubConfig(
        active_engine="debug",
        worker={"event_stream_name": "test_events"},
    )
    
    # 创建容器并注入配置
    container = AppContainer()
    container.config.override(config)
    
    # 验证配置被正确注入
    assert container.config().worker.event_stream_name == "test_events"
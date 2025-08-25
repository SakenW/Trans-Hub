# packages/server/tests/integration/di/test_container_no_redis_integration.py
"""
集成测试：验证 DI 容器在未配置 Redis 时的完整初始化流程。
"""

import os
import tempfile
from pathlib import Path

import pytest

from trans_hub.bootstrap.init import bootstrap_app
from trans_hub.config import TransHubConfig
from trans_hub.di.container import AppContainer


@pytest.fixture
def temp_db_file():
    """创建临时数据库文件。"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name
    yield temp_path
    # 清理
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def no_redis_env(temp_db_file, monkeypatch):
    """设置无 Redis 配置的环境变量。"""
    monkeypatch.setenv("TRANS_HUB_DATABASE__URL", f"sqlite+aiosqlite:///{temp_db_file}")
    monkeypatch.setenv("TRANS_HUB_REDIS__URL", "")  # 空的 Redis URL
    monkeypatch.setenv("TRANS_HUB_ACTIVE_ENGINE", "debug")


def test_container_initialization_without_redis(temp_db_file):
    """测试在未配置 Redis 时 DI 容器能够正常初始化。"""
    # 创建无 Redis 配置
    config = TransHubConfig(
        database={
            "url": f"sqlite+aiosqlite:///{temp_db_file}",
            "default_schema": "public",
        },
        redis={
            "url": "",  # 空的 Redis URL
            "key_prefix": "test:",
        },
        active_engine="debug",
    )
    
    # 创建容器并覆盖配置
    container = AppContainer()
    container.config.override(config)
    
    # 验证配置正确加载
    assert config.redis.url == ""
    assert config.active_engine == "debug"
    
    # 验证容器初始化成功
    assert container is not None
    
    # 验证 stream_producer 为 None（因为没有 Redis）
    # 这是关键测试：确保在无 Redis 配置时不会抛出连接错误
    stream_producer = container.stream_producer()
    assert stream_producer is None
    
    # 验证其他核心服务仍能正常创建
    translation_processor = container.translation_processor()
    assert translation_processor is not None
    assert translation_processor._stream_producer is None
    
    # 验证 coordinator 能够正常创建
    coordinator = container.coordinator()
    assert coordinator is not None


def test_container_initialization_with_redis_url_but_no_connection():
    """测试配置了 Redis URL 但无法连接时的行为。"""
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db_path = f.name
    
    try:
        # 创建有 Redis URL 但无法连接的配置
        config = TransHubConfig(
            database={
                "url": f"sqlite+aiosqlite:///{temp_db_path}",
                "default_schema": "public",
            },
            redis={
                "url": "redis://localhost:9999",  # 不存在的 Redis 服务
                "key_prefix": "test:",
            },
            active_engine="debug",
        )
        
        # 创建容器
        container = AppContainer()
        container.config.override(config)
        
        # 在这种情况下，stream_producer 的创建应该会尝试连接 Redis
        # 但由于我们使用了懒加载，只有在实际调用时才会尝试连接
        # 这里我们只验证 stream_producer 不是 None（因为有 Redis URL）
        stream_producer = container.stream_producer()
        assert stream_producer is not None
        
    finally:
        if os.path.exists(temp_db_path):
            os.unlink(temp_db_path)
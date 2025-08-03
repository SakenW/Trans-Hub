# tests/integration/conftest.py
"""为所有集成测试提供共享的、真实的 Fixtures。

此 conftest.py 文件中的 Fixtures 用于创建真实的、有副作用的测试环境，
例如创建临时数据库文件、初始化真实的 Coordinator 等。
它们被所有 `tests/integration/` 子目录下的测试共享。
"""

import os
import shutil
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from trans_hub import Coordinator, EngineName, TransHubConfig
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engine_registry import discover_engines
from trans_hub.interfaces import PersistenceHandler
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import create_persistence_handler

# 在测试收集阶段初始化日志和引擎发现
print()
load_dotenv()
setup_logging(log_level=os.getenv("TEST_LOG_LEVEL", "INFO"), log_format="console")
discover_engines()

TEST_DIR = Path(__file__).parent.parent / "test_output"


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    """配置全局测试环境，对整个测试会话生效一次。"""
    TEST_DIR.mkdir(exist_ok=True)
    yield
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)


@pytest.fixture
def test_config() -> TransHubConfig:
    """为每个测试提供一个隔离的 TransHubConfig 实例。"""
    db_file = f"e2e_test_{os.urandom(4).hex()}.db"
    return TransHubConfig(
        database_url=f"sqlite:///{TEST_DIR / db_file}",
        # v3.1 最终修复：使用 EngineName 枚举成员，而不是字符串
        active_engine=EngineName.DEBUG,
        source_lang="en",
    )


@pytest_asyncio.fixture
async def coordinator(
    test_config: TransHubConfig,
) -> AsyncGenerator[Coordinator, None]:
    """提供一个完全初始化、可用于端到端测试的真实 Coordinator 实例。"""
    db_path = test_config.db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    apply_migrations(db_path)

    handler: PersistenceHandler = create_persistence_handler(test_config)
    coord = Coordinator(config=test_config, persistence_handler=handler)
    await coord.initialize()

    yield coord

    await coord.close()
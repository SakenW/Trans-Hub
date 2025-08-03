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

from trans_hub import Coordinator, TransHubConfig
from trans_hub.config import EngineName
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.interfaces import PersistenceHandler
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import create_persistence_handler

# 在测试会话开始时加载环境变量并配置一次日志
load_dotenv()
setup_logging(log_level=os.getenv("TEST_LOG_LEVEL", "INFO"), log_format="console")

TEST_DIR = Path(__file__).parent.parent / "test_output"


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    """
    配置全局测试环境，对整个测试会话生效一次。

    在所有测试开始前创建测试输出目录，在所有测试结束后清理该目录。

    Yields:
        None
    """
    TEST_DIR.mkdir(exist_ok=True)
    yield
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)


@pytest.fixture
def test_config() -> TransHubConfig:
    """
    为每个测试提供一个隔离的 TransHubConfig 实例。

    每个配置都指向一个位于测试目录下的、名称唯一的全新数据库文件，
    以防止测试之间的状态污染。

    Returns:
        一个隔离的 TransHubConfig 实例。
    """
    db_file = f"e2e_test_{os.urandom(4).hex()}.db"
    return TransHubConfig(
        database_url=f"sqlite:///{TEST_DIR / db_file}",
        active_engine=EngineName.DEBUG,
        source_lang="en",
    )


@pytest_asyncio.fixture
async def coordinator(
    test_config: TransHubConfig,
) -> AsyncGenerator[Coordinator, None]:
    """
    提供一个完全初始化、可用于端到端测试的真实 Coordinator 实例。

    这个 fixture 负责：
    1. 使用项目自身的 `apply_migrations` 函数来创建最新的数据库 schema。
    2. 创建并初始化一个真实的 `Coordinator` 实例。
    3. 在测试结束后，优雅地关闭 `Coordinator` 和相关资源。

    Args:
        test_config: 来自 `test_config` fixture 的配置实例。

    Yields:
        一个已初始化的 Coordinator 实例。
    """
    db_path = test_config.db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    apply_migrations(db_path)

    handler: PersistenceHandler = create_persistence_handler(test_config)
    coord = Coordinator(config=test_config, persistence_handler=handler)
    await coord.initialize()

    yield coord

    await coord.close()
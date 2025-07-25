# tests/test_main.py (最终修正版)
"""
Trans-Hub 核心功能端到端测试。

本测试套件旨在验证 Coordinator 在一个纯异步的环境下，
能与核心组件（引擎、持久化、缓存）正确协同工作。
"""

import os
import shutil
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import structlog
from dotenv import load_dotenv

# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼【核心修改点 1：导入 SecretStr】▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
from pydantic import SecretStr

from trans_hub.config import EngineConfigs, TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engines.debug import DebugEngineConfig
from trans_hub.engines.openai import OpenAIEngineConfig
from trans_hub.engines.translators_engine import TranslatorsEngineConfig
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.types import TranslationStatus

# --- 初始化与常量定义 ---
load_dotenv()
setup_logging(log_level="INFO", log_format="console")
logger = structlog.get_logger(__name__)

TEST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "temp_test_data"))

# --- 避免魔法字符串 ---
ENGINE_DEBUG = "debug"
ENGINE_TRANSLATORS = "translators"
ENGINE_OPENAI = "openai"


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_suite():
    """在整个测试模块运行前后，创建并清理临时数据目录。"""
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR)
    yield
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)


@pytest.fixture
def test_config() -> TransHubConfig:
    """提供一个隔离的、用于测试的 TransHubConfig 实例。"""
    db_file = f"test_{os.urandom(4).hex()}.db"

    openai_api_key_str = os.getenv("TH_OPENAI_API_KEY", "dummy-key-for-mypy-and-setup")

    return TransHubConfig(
        database_url=f"sqlite:///{os.path.join(TEST_DIR, db_file)}",
        active_engine=ENGINE_DEBUG,
        source_lang="en",
        engine_configs=EngineConfigs(
            debug=DebugEngineConfig(),
            translators=TranslatorsEngineConfig(),
            # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼【核心修改点 2：将 str 包装为 SecretStr】▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
            openai=OpenAIEngineConfig(openai_api_key=SecretStr(openai_api_key_str)),
        ),
    )


@pytest_asyncio.fixture
async def migrated_db_handler(
    test_config: TransHubConfig,
) -> AsyncGenerator[DefaultPersistenceHandler, None]:
    """提供一个经过数据库迁移的持久化处理器实例。"""
    apply_migrations(test_config.db_path)
    handler = DefaultPersistenceHandler(db_path=test_config.db_path)
    await handler.connect()
    yield handler
    await handler.close()


@pytest_asyncio.fixture
async def coordinator(
    test_config: TransHubConfig, migrated_db_handler: DefaultPersistenceHandler
) -> AsyncGenerator[Coordinator, None]:
    """提供一个功能完备的 Coordinator 实例用于测试。"""
    coord = Coordinator(config=test_config, persistence_handler=migrated_db_handler)
    coord.initialized = True
    yield coord


# ... (文件余下部分保持不变) ...


@pytest.mark.asyncio
async def test_debug_engine_workflow(coordinator: Coordinator):
    """测试 Debug 引擎的基本请求、处理和缓存流程。"""
    text = "这是一个简单的测试"
    target_lang = "dbg"
    business_id = "test.debug.1"

    await coordinator.request([target_lang], text, business_id)
    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]

    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.TRANSLATED
    assert result.translated_content == f"Translated({text}) to {target_lang}"

    await coordinator.request([target_lang], text, business_id)
    cached_results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]
    assert len(cached_results) == 0, "已翻译的内容不应被再次处理"


@pytest.mark.asyncio
async def test_translators_engine_workflow(coordinator: Coordinator):
    """测试切换到 Translators 引擎并执行真实翻译。"""
    coordinator.switch_engine(ENGINE_TRANSLATORS)
    text = "The quick brown fox jumps over the lazy dog."
    target_lang = "zh-CN"

    await coordinator.request([target_lang], text)
    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]

    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.TRANSLATED
    translated_content = result.translated_content
    assert translated_content is not None

    logger.info("引擎翻译结果", engine=ENGINE_TRANSLATORS, result=translated_content)
    assert "狐狸" in translated_content and "狗" in translated_content


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("TH_OPENAI_API_KEY"), reason="需要设置 TH_OPENAI_API_KEY 环境变量"
)
async def test_openai_engine_workflow(coordinator: Coordinator):
    """测试切换到 OpenAI 引擎并执行真实翻译（如果配置了 API Key）。"""
    coordinator.switch_engine(ENGINE_OPENAI)
    text = "The art of programming is the skill of controlling complexity."
    target_lang = "fr"

    await coordinator.request([target_lang], text, source_lang="en")
    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]

    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.TRANSLATED
    translated_content = result.translated_content
    assert translated_content is not None

    logger.info("引擎翻译结果", engine=ENGINE_OPENAI, result=translated_content)
    assert "complexité" in translated_content.lower()


@pytest.mark.asyncio
async def test_garbage_collection_workflow(coordinator: Coordinator):
    """测试垃圾回收功能是否能正确清理过期的记录。"""
    await coordinator.request(["ja"], "active item", "active.item")
    await coordinator.request(["ja"], "legacy item", "legacy.item")

    _ = [res async for res in coordinator.process_pending_translations("ja")]

    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
    async with coordinator.handler.transaction() as cursor:
        await cursor.execute(
            "UPDATE th_sources SET last_seen_at = ? WHERE business_id = ?",
            (two_days_ago.isoformat(), "legacy.item"),
        )

    gc_stats = await coordinator.run_garbage_collection(expiration_days=1)

    assert gc_stats.get("deleted_sources", 0) == 1

    async with coordinator.handler.transaction() as cursor:
        await cursor.execute("SELECT business_id FROM th_sources")
        remaining_records = {row["business_id"] for row in await cursor.fetchall()}

    assert "legacy.item" not in remaining_records
    assert "active.item" in remaining_records


if __name__ == "__main__":
    pytest.main(["-s", "-v", __file__])

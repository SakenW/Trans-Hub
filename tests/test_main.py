# tests/test_main.py
"""
Trans-Hub 核心功能端到端测试。
此版本适配了 v2.1+ 的动态注册配置模式。
"""

import os
import shutil
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio
import structlog
from dotenv import load_dotenv
from pydantic import HttpUrl, SecretStr

from trans_hub.config import EngineConfigs, TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engines.debug import DebugEngineConfig
from trans_hub.engines.openai import OpenAIEngineConfig
from trans_hub.engines.translators_engine import TranslatorsEngineConfig
from trans_hub.interfaces import PersistenceHandler
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.types import TranslationStatus

# --- 初始化与常量定义 ---
load_dotenv()
setup_logging(log_level="INFO", log_format="console")
logger = structlog.get_logger(__name__)

TEST_DIR = Path(__file__).parent / "test_output"
ENGINE_DEBUG = "debug"
ENGINE_TRANSLATORS = "translators"
ENGINE_OPENAI = "openai"


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """在所有测试开始前运行一次，创建测试目录。"""
    TEST_DIR.mkdir(exist_ok=True)
    yield
    shutil.rmtree(TEST_DIR)


@pytest.fixture
def test_config() -> TransHubConfig:
    """提供一个隔离的、用于测试的 TransHubConfig 实例。"""
    db_file = f"test_{os.urandom(4).hex()}.db"

    openai_api_key_str = os.getenv("TH_OPENAI_API_KEY", "dummy-key-for-testing")
    openai_endpoint_str = os.getenv("TH_OPENAI_ENDPOINT") or "https://api.openai.com/v1"

    # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 核心修复点 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
    # 我们必须手动为所有将在测试中使用的引擎提供配置，
    # 因为 TransHubConfig 的验证器只会自动创建 active_engine 的配置。
    return TransHubConfig(
        database_url=f"sqlite:///{TEST_DIR / db_file}",
        active_engine=ENGINE_DEBUG,
        source_lang="en",
        engine_configs=EngineConfigs(
            debug=DebugEngineConfig(),
            translators=TranslatorsEngineConfig(),
            openai=OpenAIEngineConfig(
                openai_api_key=SecretStr(openai_api_key_str),
                openai_endpoint=HttpUrl(openai_endpoint_str),
            ),
        ),
    )
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲


@pytest_asyncio.fixture
async def coordinator(test_config: TransHubConfig) -> AsyncGenerator[Coordinator, None]:
    """提供一个完全初始化并准备就绪的 Coordinator 实例。"""
    apply_migrations(test_config.db_path)
    handler: PersistenceHandler = DefaultPersistenceHandler(db_path=test_config.db_path)
    coord = Coordinator(config=test_config, persistence_handler=handler)
    await coord.initialize()
    yield coord
    await coord.close()


# --- 测试用例 ---


@pytest.mark.asyncio
async def test_debug_engine_workflow(coordinator: Coordinator):
    """测试 Debug 引擎的基本请求-处理工作流。"""
    text = "Hello"
    target_lang = "zh-CN"
    business_id = "test.debug.hello"

    await coordinator.request(
        target_langs=[target_lang], text_content=text, business_id=business_id
    )

    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]

    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.TRANSLATED
    assert result.original_content == text
    assert result.translated_content == f"Translated({text}) to {target_lang}"
    assert result.business_id == business_id
    assert result.engine == ENGINE_DEBUG


@pytest.mark.skipif(
    not os.getenv("TH_OPENAI_API_KEY")
    or os.getenv("TH_OPENAI_API_KEY") == "dummy-key-for-testing",
    reason="需要设置一个真实的 TH_OPENAI_API_KEY 环境变量",
)
@pytest.mark.asyncio
async def test_openai_engine_workflow(coordinator: Coordinator):
    """测试 OpenAI 引擎的工作流（需要真实 API Key）。"""
    coordinator.switch_engine(ENGINE_OPENAI)
    text = "Star"
    target_lang = "fr"
    context = {"system_prompt": "Translate the following celestial body."}

    await coordinator.request(
        target_langs=[target_lang],
        text_content=text,
        context=context,
        source_lang="en",
    )

    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]

    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.TRANSLATED
    assert result.translated_content is not None
    assert "toile" in result.translated_content.lower()
    assert result.engine == ENGINE_OPENAI


@pytest.mark.asyncio
async def test_translators_engine_workflow(coordinator: Coordinator):
    """测试 Translators 引擎的工作流。"""
    coordinator.switch_engine(ENGINE_TRANSLATORS)
    text = "Moon"
    target_lang = "de"

    await coordinator.request(target_langs=[target_lang], text_content=text)
    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]

    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.TRANSLATED
    assert result.translated_content == "Mond"
    assert result.engine == ENGINE_TRANSLATORS


@pytest.mark.asyncio
async def test_garbage_collection_workflow(coordinator: Coordinator):
    """测试垃圾回收（GC）的逻辑。"""
    await coordinator.request(
        target_langs=["zh-CN"], text_content="fresh item", business_id="item.fresh"
    )
    await coordinator.request(
        target_langs=["zh-CN"], text_content="stale item", business_id="item.stale"
    )
    _ = [res async for res in coordinator.process_pending_translations("zh-CN")]

    handler = coordinator.handler
    assert isinstance(handler, DefaultPersistenceHandler)
    async with aiosqlite.connect(handler.db_path) as db:
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await db.execute(
            "UPDATE th_sources SET last_seen_at = ? WHERE business_id = ?",
            (two_days_ago, "item.stale"),
        )
        await db.commit()

    await coordinator.request(
        target_langs=["zh-CN"], text_content="fresh item", business_id="item.fresh"
    )

    report = await coordinator.run_garbage_collection(dry_run=False, expiration_days=1)

    assert report["deleted_sources"] == 1

    report_after = await coordinator.run_garbage_collection(
        dry_run=True, expiration_days=1
    )
    assert report_after["deleted_sources"] == 0

    async with aiosqlite.connect(handler.db_path) as db:
        async with db.execute("SELECT business_id FROM th_sources") as cursor:
            rows = await cursor.fetchall()
            remaining_ids = {row[0] for row in rows}
            assert remaining_ids == {"item.fresh"}


if __name__ == "__main__":
    pytest.main(["-s", "-v", __file__])

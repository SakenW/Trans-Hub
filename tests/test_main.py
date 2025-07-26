# tests/test_main.py
"""Trans-Hub 核心功能端到端测试 (v2.3.0)。"""

import asyncio
import os
import shutil
import time
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


# --- Fixtures ---


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """在所有测试开始前运行一次，创建测试目录。"""
    TEST_DIR.mkdir(exist_ok=True)
    yield
    shutil.rmtree(TEST_DIR)


@pytest.fixture
def test_config() -> TransHubConfig:
    """
    提供一个隔离的、包含了所有测试所需引擎配置的实例。
    这使得测试不依赖于 .env 文件，行为完全可预测。
    """
    db_file = f"test_{os.urandom(4).hex()}.db"

    openai_api_key_str = os.getenv("TH_OPENAI_API_KEY", "dummy-key-for-testing")
    openai_endpoint_str = os.getenv("TH_OPENAI_ENDPOINT") or "https://api.openai.com/v1"

    engine_configs_data = {
        "debug": DebugEngineConfig(),
        "translators": TranslatorsEngineConfig(),
        "openai": OpenAIEngineConfig(
            openai_api_key=SecretStr(openai_api_key_str),
            openai_endpoint=HttpUrl(openai_endpoint_str),
        ),
    }
    # 在 mypy 中，动态模型可能会引发类型错误，对于测试设置，这是可接受的
    engine_configs_instance = EngineConfigs(**engine_configs_data)  # type: ignore

    return TransHubConfig(
        database_url=f"sqlite:///{TEST_DIR / db_file}",
        active_engine=ENGINE_DEBUG,
        source_lang="en",
        engine_configs=engine_configs_instance,
    )


@pytest_asyncio.fixture
async def coordinator(test_config: TransHubConfig) -> AsyncGenerator[Coordinator, None]:
    """提供一个完全初始化并准备就绪的 Coordinator 实例。"""
    apply_migrations(test_config.db_path)
    handler: PersistenceHandler = DefaultPersistenceHandler(db_path=test_config.db_path)
    coord = Coordinator(config=test_config, persistence_handler=handler)
    await coord.initialize()
    yield coord
    await coord.close()


# --- v2.2.0 原有测试用例 (保持不变) ---


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


# --- v2.3.0 新增测试用例 ---


@pytest.mark.asyncio
async def test_force_retranslate_api(coordinator: Coordinator):
    """测试强制重翻API (`force_retranslate=True`)。"""
    text = "Sun"
    target_lang = "es"

    # 1. 正常翻译并完成
    await coordinator.request(target_langs=[target_lang], text_content=text)
    _ = [res async for res in coordinator.process_pending_translations(target_lang)]

    # 2. 确认已翻译
    result = await coordinator.get_translation(text, target_lang)
    assert result is not None
    assert result.status == TranslationStatus.TRANSLATED
    assert result.translated_content == f"Translated({text}) to {target_lang}"

    # 3. 使用 force_retranslate 强制重新请求
    await coordinator.request(
        target_langs=[target_lang], text_content=text, force_retranslate=True
    )

    # 4. 检查数据库，任务状态应该被重置为 PENDING
    handler = coordinator.handler
    assert isinstance(handler, DefaultPersistenceHandler)
    async with aiosqlite.connect(handler.db_path) as db:
        async with db.execute(
            "SELECT T.status FROM th_translations T JOIN th_content C ON T.content_id = C.id WHERE C.value = ? AND T.lang_code = ?",
            (text, target_lang),
        ) as cursor:
            row = await cursor.fetchone()
            # 核心修正：在使用 row 之前，断言它不为 None
            assert row is not None, "数据库中未找到强制重翻后的任务记录"
            assert row[0] == TranslationStatus.PENDING.value

    # 5. 再次处理，应该能再次翻译
    results_rerun = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]
    assert len(results_rerun) == 1
    assert results_rerun[0].status == TranslationStatus.TRANSLATED


@pytest.mark.asyncio
async def test_self_healing_of_stale_tasks(test_config: TransHubConfig):
    """测试'僵尸任务'自愈机制。"""
    # 1. 初始化一个协调器并请求一个任务
    apply_migrations(test_config.db_path)
    handler = DefaultPersistenceHandler(db_path=test_config.db_path)
    coord1 = Coordinator(config=test_config, persistence_handler=handler)
    await coord1.initialize()
    await coord1.request(target_langs=["fr"], text_content="Stale Task")

    # 2. 手动将任务状态设置为 TRANSLATING 来模拟崩溃
    async with aiosqlite.connect(test_config.db_path) as db:
        await db.execute(
            "UPDATE th_translations SET status = ?",
            (TranslationStatus.TRANSLATING.value,),
        )
        await db.commit()
    await coord1.close()

    # 3. 创建一个新的协调器实例，它的 initialize() 应该会自动修复僵尸任务
    handler2 = DefaultPersistenceHandler(db_path=test_config.db_path)
    coord2 = Coordinator(config=test_config, persistence_handler=handler2)
    await coord2.initialize()  # 自愈发生在这里

    # 4. 验证任务状态是否已重置为 PENDING
    async with aiosqlite.connect(test_config.db_path) as db:
        async with db.execute("SELECT status FROM th_translations") as cursor:
            row = await cursor.fetchone()
            # 核心修正：在使用 row 之前，断言它不为 None
            assert row is not None, "数据库中未找到本应被自愈的任务"
            assert row[0] == TranslationStatus.PENDING.value

    await coord2.close()


@pytest.mark.asyncio
async def test_concurrent_request_throttling(test_config: TransHubConfig):
    """测试内置的请求节流功能。"""
    apply_migrations(test_config.db_path)
    handler = DefaultPersistenceHandler(db_path=test_config.db_path)
    # 1. 创建一个最大并发为1的协调器
    coord = Coordinator(
        config=test_config, persistence_handler=handler, max_concurrent_requests=1
    )
    await coord.initialize()

    processing_times = []

    # 替换内部方法以记录时间并模拟耗时
    original_internal_request = coord._request_internal

    async def mocked_internal_request(*args, **kwargs):
        processing_times.append(("start", time.monotonic()))
        await asyncio.sleep(0.1)  # 模拟I/O耗时
        await original_internal_request(*args, **kwargs)
        processing_times.append(("end", time.monotonic()))

    coord._request_internal = mocked_internal_request  # type: ignore

    # 2. 同时发起3个请求
    tasks = [
        coord.request(target_langs=["de"], text_content=f"text {i}") for i in range(3)
    ]
    await asyncio.gather(*tasks)

    # 3. 分析时间戳，验证请求是顺序执行的
    assert len(processing_times) == 6  # 3 starts, 3 ends

    starts = sorted([t for event, t in processing_times if event == "start"])
    ends = sorted([t for event, t in processing_times if event == "end"])

    # 第一个任务的结束时间，应该早于第二个任务的开始时间
    assert ends[0] < starts[1]
    # 第二个任务的结束时间，应该早于第三个任务的开始时间
    assert ends[1] < starts[2]

    await coord.close()


if __name__ == "__main__":
    pytest.main(["-s", "-v", __file__])

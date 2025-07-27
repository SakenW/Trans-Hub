# tests/test_main.py
"""
Trans-Hub 核心功能的端到端测试。

本测试套件旨在通过模拟真实使用场景，验证 Coordinator 与各个子系统
（如持久化、翻译引擎、缓存等）的集成工作是否正常。
它覆盖了从请求入队、处理、结果获取到系统维护（如垃圾回收）的完整生命周期。
"""

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
    """
    在整个测试会话开始前准备测试目录，并在会话结束后自动清理。
    这是一个会话级别的、自动运行的 Fixture。
    """
    TEST_DIR.mkdir(exist_ok=True)
    logger.info("测试输出目录已创建", path=str(TEST_DIR))
    yield
    shutil.rmtree(TEST_DIR)
    logger.info("测试输出目录已清理", path=str(TEST_DIR))


@pytest.fixture
def test_config() -> TransHubConfig:
    """
    为每个测试用例提供一个隔离的、包含所有引擎配置的 TransHubConfig 实例。

    这确保了每个测试都运行在独立的数据库上，避免了相互干扰，
    并通过预设的引擎配置使得测试行为完全可预测，不依赖于外部 .env 文件。
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
    # 对于 Pydantic 动态模型，mypy 可能会报告类型错误，这在测试设置中是可接受的。
    engine_configs_instance = EngineConfigs(**engine_configs_data)  # type: ignore

    return TransHubConfig(
        database_url=f"sqlite:///{TEST_DIR / db_file}",
        active_engine=ENGINE_DEBUG,
        source_lang="en",
        engine_configs=engine_configs_instance,
    )


@pytest_asyncio.fixture
async def coordinator(test_config: TransHubConfig) -> AsyncGenerator[Coordinator, None]:
    """
    提供一个完全初始化并准备就绪的 Coordinator 实例。

    此 Fixture 会自动处理数据库的创建、迁移、连接以及在测试结束后的安全关闭，
    极大地简化了测试用例的编写。
    """
    apply_migrations(test_config.db_path)
    handler: PersistenceHandler = DefaultPersistenceHandler(db_path=test_config.db_path)
    coord = Coordinator(config=test_config, persistence_handler=handler)
    await coord.initialize()
    yield coord
    await coord.close()


# --- v2.2.0 原有测试用例 ---


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
    reason="需要设置一个真实的 TH_OPENAI_API_KEY 环境变量以运行此测试。",
)
@pytest.mark.asyncio
async def test_openai_engine_workflow(coordinator: Coordinator):
    """测试 OpenAI 引擎的端到端工作流（需要真实 API Key）。"""
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
    """测试 Translators 引擎（基于 'translators' 库）的端到端工作流。"""
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
    """测试垃圾回收（GC）能否正确识别并删除过期的源记录。"""
    # 安排：创建一条新鲜记录和一条将被标记为过期的记录
    await coordinator.request(
        target_langs=["zh-CN"], text_content="fresh item", business_id="item.fresh"
    )
    await coordinator.request(
        target_langs=["zh-CN"], text_content="stale item", business_id="item.stale"
    )
    _ = [res async for res in coordinator.process_pending_translations("zh-CN")]

    # 手动将 'item.stale' 的最后访问时间设置为2天前
    handler = coordinator.handler
    assert isinstance(handler, DefaultPersistenceHandler)
    async with aiosqlite.connect(handler.db_path) as db:
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await db.execute(
            "UPDATE th_sources SET last_seen_at = ? WHERE business_id = ?",
            (two_days_ago, "item.stale"),
        )
        await db.commit()

    # 再次请求新鲜记录，模拟活跃使用
    await coordinator.request(
        target_langs=["zh-CN"], text_content="fresh item", business_id="item.fresh"
    )

    # 行动：运行垃圾回收，清理1天前的数据
    report = await coordinator.run_garbage_collection(dry_run=False, expiration_days=1)

    # 断言：应删除1条过期记录
    assert report["deleted_sources"] == 1

    # 再次空跑GC，不应再删除任何记录
    report_after = await coordinator.run_garbage_collection(
        dry_run=True, expiration_days=1
    )
    assert report_after["deleted_sources"] == 0

    # 验证数据库状态，只剩下新鲜记录
    async with aiosqlite.connect(handler.db_path) as db:
        async with db.execute("SELECT business_id FROM th_sources") as cursor:
            rows = await cursor.fetchall()
            remaining_ids = {row[0] for row in rows}
            assert remaining_ids == {"item.fresh"}


# --- v2.3.0 新增测试用例 ---


@pytest.mark.asyncio
async def test_force_retranslate_api(coordinator: Coordinator):
    """测试强制重翻API (`force_retranslate=True`) 是否能将已完成的任务重置为 PENDING。"""
    text = "Sun"
    target_lang = "es"

    # 1. 正常翻译并完成
    await coordinator.request(target_langs=[target_lang], text_content=text)
    _ = [res async for res in coordinator.process_pending_translations(target_lang)]

    # 2. 确认已翻译
    result = await coordinator.get_translation(text, target_lang)
    assert result is not None, "首次翻译后未能获取到结果"
    assert result.status == TranslationStatus.TRANSLATED
    assert result.translated_content == f"Translated({text}) to {target_lang}"

    # 3. 使用 `force_retranslate=True` 强制重新请求
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
            assert row is not None, "数据库中未找到强制重翻后的任务记录"
            assert row[0] == TranslationStatus.PENDING.value

    # 5. 再次处理，应该能再次翻译成功
    results_rerun = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]
    assert len(results_rerun) == 1
    assert results_rerun[0].status == TranslationStatus.TRANSLATED


@pytest.mark.asyncio
async def test_self_healing_of_stale_tasks(test_config: TransHubConfig):
    """
    测试当一个任务在 'TRANSLATING' 状态卡住时（模拟应用崩溃），
    系统能否在下次启动时自动将其重置为 'PENDING'。
    """
    # 1. 启动第一个 Coordinator，请求一个任务，然后手动模拟崩溃
    apply_migrations(test_config.db_path)
    handler1 = DefaultPersistenceHandler(db_path=test_config.db_path)
    coord1 = Coordinator(config=test_config, persistence_handler=handler1)
    await coord1.initialize()
    await coord1.request(target_langs=["fr"], text_content="Stale Task")

    async with aiosqlite.connect(test_config.db_path) as db:
        await db.execute(
            "UPDATE th_translations SET status = ?",
            (TranslationStatus.TRANSLATING.value,),
        )
        await db.commit()
    await coord1.close()

    # 2. 启动第二个 Coordinator，它的 initialize() 应该会自动触发自愈
    handler2 = DefaultPersistenceHandler(db_path=test_config.db_path)
    coord2 = Coordinator(config=test_config, persistence_handler=handler2)
    await coord2.initialize()  # 自愈逻辑在此处执行

    # 3. 验证任务状态是否已成功重置为 PENDING
    async with aiosqlite.connect(test_config.db_path) as db:
        async with db.execute("SELECT status FROM th_translations") as cursor:
            row = await cursor.fetchone()
            assert row is not None, "数据库中未找到本应被自愈的任务"
            assert row[0] == TranslationStatus.PENDING.value

    await coord2.close()


@pytest.mark.asyncio
async def test_concurrent_request_throttling(test_config: TransHubConfig):
    """测试当设置了 `max_concurrent_requests` 时，Coordinator 的请求节流功能是否生效。"""
    apply_migrations(test_config.db_path)
    handler = DefaultPersistenceHandler(db_path=test_config.db_path)
    # 1. 创建一个最大并发为 1 的协调器
    coord = Coordinator(
        config=test_config, persistence_handler=handler, max_concurrent_requests=1
    )
    await coord.initialize()

    processing_times = []

    # 2. 替换内部请求方法以记录时间并模拟耗时
    original_internal_request = coord._request_internal

    async def mocked_internal_request(*args, **kwargs):
        processing_times.append(("start", time.monotonic()))
        await asyncio.sleep(0.1)  # 模拟I/O耗时
        await original_internal_request(*args, **kwargs)
        processing_times.append(("end", time.monotonic()))

    coord._request_internal = mocked_internal_request  # type: ignore

    # 3. 同时并发发起 3 个请求
    tasks = [
        coord.request(target_langs=["de"], text_content=f"text {i}") for i in range(3)
    ]
    await asyncio.gather(*tasks)

    # 4. 分析时间戳，验证请求是顺序执行的
    assert len(processing_times) == 6  # 3 个开始事件, 3 个结束事件

    starts = sorted([t for event, t in processing_times if event == "start"])
    ends = sorted([t for event, t in processing_times if event == "end"])

    # 第一个任务的结束时间，必须早于第二个任务的开始时间
    assert ends[0] < starts[1]
    # 第二个任务的结束时间，必须早于第三个任务的开始时间
    assert ends[1] < starts[2]

    await coord.close()


if __name__ == "__main__":
    pytest.main(["-s", "-v", __file__])

# run_coordinator_test.py (基于v1.1.0 修正的核心逻辑)
import datetime
import os
import shutil

# 第三方库导入
import structlog
from dotenv import load_dotenv

# 本地库导入
from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler

# 获取一个 logger
log = structlog.get_logger()

# 定义一个临时的测试目录和数据库文件
TEST_DIR = "temp_test_data"
DB_FILE = os.path.join(TEST_DIR, "test_transhub.db")


def setup_test_environment():
    """创建一个干净的测试环境。"""
    log.info("--- 正在设置测试环境 ---")
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR)
    apply_migrations(DB_FILE)
    log.info("测试环境已就绪。")


def cleanup_test_environment():
    """清理测试环境。"""
    log.info("--- 正在清理测试环境 ---")
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    log.info("测试环境已清理。")


def test_gc_workflow():
    """一个专注、健壮的垃圾回收 (GC) 测试函数。"""
    log.info("\n--- 开始测试 GC ---")

    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE}",
        active_engine="debug",
        gc_retention_days=1,  # 使用保留期为1天进行测试
    )
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        # 1. 创建一个活跃的 和 一个将要过时的 business_id
        coordinator.request(
            target_langs=["jp"],
            text_content="active item",
            business_id="active.item",
        )
        coordinator.request(
            target_langs=["jp"],
            text_content="legacy item",
            business_id="legacy.item",
        )
        list(coordinator.process_pending_translations(target_lang="jp"))
        log.info("初始数据已创建并翻译。")

        # 2. 手动修改 'legacy.item' 的时间戳，使其明确地“过时”
        # 核心修正：使用 datetime.datetime.now, datetime.timedelta, datetime.timezone
        past_datetime = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(days=2)
        with handler.transaction() as cursor:
            cursor.execute(
                "UPDATE th_sources SET last_seen_at = ? WHERE business_id = ?",
                (past_datetime.isoformat(), "legacy.item"),
            )
        log.info("'legacy.item' 的时间戳已更新为两天前。")

        # 3. 运行 GC 并验证
        gc_stats = coordinator.run_garbage_collection(dry_run=False)
        assert gc_stats["deleted_sources"] == 1, "GC 应该实际清理了1个过时的源"

        with handler.transaction() as cursor:
            cursor.execute("SELECT business_id FROM th_sources")
            remaining_bids = {row[0] for row in cursor.fetchall()}
            assert remaining_bids == {"active.item"}, "GC后应只剩下 'active.item'"

        log.info("✅ 垃圾回收 (GC) 测试成功！")

    finally:
        if coordinator:
            coordinator.close()


def main():
    """运行所有测试。"""
    load_dotenv()
    setup_logging(log_level="INFO")
    root_log = structlog.get_logger("test_runner")

    try:
        root_log.info("======== Trans-Hub v1.1 功能验证开始 ========")
        setup_test_environment()
        test_gc_workflow()
        root_log.info("🎉======== 所有测试成功通过！Trans-Hub v1.1 功能验证完成！========🎉")
    except Exception:
        root_log.error("❌ 测试过程中发生未捕获的异常！", exc_info=True)
        raise
    finally:
        cleanup_test_environment()


if __name__ == "__main__":
    main()

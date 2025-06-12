"""
run_coordinator_test.py (v0.5)

一个用于测试 Coordinator 端到端工作流的脚本。
此版本增加了对垃圾回收 (GC) 功能的验证。
"""
import logging
import os
import sqlite3
import time

from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engines.debug import DebugEngine, DebugEngineConfig
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.rate_limiter import RateLimiter
from trans_hub.types import TranslationStatus

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logging.getLogger("trans_hub").setLevel(logging.INFO)

    DB_FILE = "transhub_gc_test.db"
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    apply_migrations(DB_FILE)
    
    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    coordinator = Coordinator(
        persistence_handler=handler,
        engines={"debug": DebugEngine(DebugEngineConfig())},
        active_engine_name="debug"
    )
    
    try:
        # === 步骤 1: 准备 GC 测试数据 ===
        print("\n" + "=" * 20 + " 步骤 1: 准备 GC 测试数据 " + "=" * 20)
        
        # 1. 一个过时的源: last_seen_at 会在很久以前
        # 2. 一个活跃的源: last_seen_at 是现在
        # 3. 一个孤立的内容: 从未被任何源或翻译引用
        
        with handler.transaction() as cursor:
            # 插入内容
            cursor.execute("INSERT INTO th_content (id, value, created_at) VALUES (1, 'old_content', '2020-01-01 10:00:00')")
            cursor.execute("INSERT INTO th_content (id, value) VALUES (2, 'active_content')")
            cursor.execute("INSERT INTO th_content (id, value, created_at) VALUES (3, 'orphan_content', '2020-01-01 11:00:00')")
            
            # 插入源
            cursor.execute("INSERT INTO th_sources (business_id, content_id, last_seen_at) VALUES ('source:old', 1, '2020-01-01 10:00:00')")
            cursor.execute("INSERT INTO th_sources (business_id, content_id, last_seen_at) VALUES ('source:active', 2, ?)", (time.strftime('%Y-%m-%d %H:%M:%S'),))
            
        print("GC 测试数据已创建。")

        # === 步骤 2: 执行 GC (dry_run模式) ===
        print("\n" + "=" * 20 + " 步骤 2: 执行 GC (dry_run) " + "=" * 20)
        # 设置一个很长的保留期，比如 1000 天
        stats_dry = coordinator.run_garbage_collection(retention_days=1000, dry_run=True)
        print(f"Dry run 统计结果: {stats_dry}")
        assert stats_dry["deleted_sources"] == 1
        assert stats_dry["deleted_content"] == 1
        print("Dry run 验证成功！")

        # === 步骤 3: 验证数据库在 dry_run 后未发生变化 ===
        print("\n" + "=" * 20 + " 步骤 3: 验证数据库在 dry_run 后状态 " + "=" * 20)
        with handler.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM th_sources")
            assert cursor.fetchone()[0] == 2
            cursor.execute("SELECT COUNT(*) FROM th_content")
            assert cursor.fetchone()[0] == 3
        print("数据库状态未变，验证成功！")

# run_coordinator_test.py

        # === 步骤 4: 执行真正的 GC ===
        print("\n" + "=" * 20 + " 步骤 4: 执行真正的 GC " + "=" * 20)
        stats_real = coordinator.run_garbage_collection(retention_days=1000, dry_run=False)
        print(f"GC 执行统计结果: {stats_real}")
        # [修正] 断言删除的源是1个，删除的内容是2个（orphan_content + old_content）
        assert stats_real["deleted_sources"] == 1
        assert stats_real["deleted_content"] == 2

        # === 步骤 5: 验证数据库在 GC 后发生变化 ===
        print("\n" + "=" * 20 + " 步骤 5: 验证数据库在 GC 后状态 " + "=" * 20)
        with handler.transaction() as cursor:
            # 过时源被删除，只剩活跃源
            cursor.execute("SELECT COUNT(*) FROM th_sources")
            assert cursor.fetchone()[0] == 1
            # 孤立内容和因源被删而孤立的内容都被删除，只剩活跃内容
            cursor.execute("SELECT COUNT(*) FROM th_content")
            assert cursor.fetchone()[0] == 1 # [修正] 3 - 2 = 1
            
            # 确认被删除的是正确的记录
            cursor.execute("SELECT value FROM th_content")
            remaining_content = {row[0] for row in cursor.fetchall()}
            assert "orphan_content" not in remaining_content
            assert "old_content" not in remaining_content # [新增] 确认 old_content 也被删了
            assert "active_content" in remaining_content
        print("数据库状态已更新，验证成功！")

        print("\n所有验证成功！垃圾回收 (GC) 功能工作正常！")

    finally:
        coordinator.close()

if __name__ == "__main__":
    main()
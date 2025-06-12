"""
run_coordinator_test.py (v0.4)

一个用于测试 Coordinator 端到端工作流的脚本。
此版本增加了对速率限制器的验证。
"""
import logging
import os
import time

from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engines.debug import DebugEngine, DebugEngineConfig
from trans_hub.persistence import DefaultPersistenceHandler
# [新] 导入速率限制器
from trans_hub.rate_limiter import RateLimiter
from trans_hub.types import TranslationStatus, TranslationResult

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # 将我们自己库的日志级别设为DEBUG，以便看到速率限制器的日志
    logging.getLogger("trans_hub").setLevel(logging.DEBUG)

    DB_FILE = "transhub_coord_test.db"
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    apply_migrations(DB_FILE)
    
    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    debug_engine = DebugEngine(config=DebugEngineConfig())
    engines = {"debug": debug_engine}

    # === [新] 初始化速率限制器 ===
    # 我们设置一个非常低的速率（每秒2个请求），以便在测试中能明显看到效果。
    # 容量为1，意味着它不能累积突发能力。
    rate_limiter = RateLimiter(refill_rate=2, capacity=1)
    print(f"\n速率限制器已创建 (RPS=2, Capacity=1)")

    # 将速率限制器注入 Coordinator
    coordinator = Coordinator(
        persistence_handler=handler,
        engines=engines,
        active_engine_name="debug",
        rate_limiter=rate_limiter, # 注入！
    )
    
    try:
        print("\n" + "=" * 20 + " 步骤 1: 准备数据 (3个任务) " + "=" * 20)
        # 我们一次性请求3个任务
        coordinator.request(target_langs=['jp'], text_content="apple")
        coordinator.request(target_langs=['jp'], text_content="banana")
        coordinator.request(target_langs=['jp'], text_content="cherry")
        print("数据准备完成。")
        
        # === [新] 测试速率限制逻辑 ===
        print("\n" + "=" * 20 + " 步骤 2: 以小批次 (batch_size=1) 执行翻译 " + "=" * 20)
        
        start_time = time.monotonic()
        
        # 我们将 batch_size 设为 1，这样 Coordinator 会对每个任务单独调用一次 translate_batch
        # 因此，它会调用3次 API，每次都需要获取令牌。
        jp_results_generator = coordinator.process_pending_translations(
            target_lang="jp",
            batch_size=1, # 强制每次只处理一个
            max_retries=0 # 关闭重试，简化测试
        )
        
        results_list = [result for result in jp_results_generator]
        
        end_time = time.monotonic()
        duration = end_time - start_time
        
        print(f"\n处理3个任务总耗时: {duration:.2f} 秒")
        
        # 验证结果
        assert len(results_list) == 3
        # 理论上，处理3个请求，速率为2rps，需要的时间：
        # 第1个: 立即执行 (桶里有1个令牌)
        # 第2个: 等待0.5秒补充1个令牌
        # 第3个: 再等待0.5秒补充1个令牌
        # 总时间应该略大于 1.0 秒。我们用一个宽松的断言。
        assert duration > 1.0, f"总耗时 {duration:.2f}s 过短，速率限制器可能未生效！"
        
        print(f"耗时符合预期，速率限制器工作正常！")
        
        print("\n所有验证成功！Coordinator 已具备速率限制能力！")

    finally:
        coordinator.close()

if __name__ == "__main__":
    main()
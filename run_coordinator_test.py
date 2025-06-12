"""
run_coordinator_test.py (v0.2)

一个用于测试 Coordinator 端到端工作流的脚本。
此版本使用 coordinator.request() 方法来准备数据。
"""
import logging
import os

# --- 导入我们自己的库和组件 ---
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engines.debug import DebugEngine, DebugEngineConfig
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.types import TranslationStatus, TranslationResult # 导入 TranslationResult
from trans_hub.utils import get_context_hash # [新] 导入哈希函数


def main():
    """主测试函数"""
    # --- 基本配置 ---
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("trans_hub").setLevel(logging.DEBUG)

    # --- 步骤 1: 初始化所有组件 ---
    print("\n" + "=" * 20 + " 步骤 1: 初始化所有组件 " + "=" * 20)
    
    DB_FILE = "transhub_coord_test.db"
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    apply_migrations(DB_FILE)
    
    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    debug_engine = DebugEngine(config=DebugEngineConfig())
    engines = {"debug": debug_engine}

    coordinator = Coordinator(
        persistence_handler=handler,
        engines=engines,
        active_engine_name="debug",
    )
    print("Coordinator 初始化成功！")
    
    try:
        # === [变更] 步骤 2: 使用 coordinator.request() 准备数据 ===
        print("\n" + "=" * 20 + " 步骤 2: 使用 request() API 准备待翻译数据 " + "=" * 20)
        
        # 场景1: UI 文本，需要翻译成日语和法语
        coordinator.request(
            target_langs=['jp', 'fr'],
            text_content="apple",
            business_id="ui.products.fruit_list.apple"
        )
        
        # 场景2: 带上下文的文本，只需要翻译成日语
        context_for_banana = {"max_length": 10}
        coordinator.request(
            target_langs=['jp'],
            text_content="banana",
            business_id="ui.products.fruit_list.banana",
            context=context_for_banana
        )
        
        # 场景3: 纯文本即席翻译，不需要 business_id
        coordinator.request(
            target_langs=['de'],
            text_content="cherry",
            business_id=None
        )
        
        print("翻译请求已登记。")
        
        # === 步骤 3: 执行核心流程 (处理日语翻译) ===
        print("\n" + "=" * 20 + " 步骤 3: 调用 process_pending_translations 处理日语任务 " + "=" * 20)
        
        jp_results_generator = coordinator.process_pending_translations(target_lang="jp")
        
        print("Coordinator 返回的实时结果:")
        results_list: List[TranslationResult] = []
        for result in jp_results_generator:
            print(f"  > {result}")
            results_list.append(result)
            
        assert len(results_list) == 2, "应该处理了2个日语任务"

        # === 步骤 4: 验证数据库最终状态 ===
        print("\n" + "=" * 20 + " 步骤 4: 验证数据库最终状态 " + "=" * 20)
        
        with handler.transaction() as cursor:
            # 验证日语任务
            cursor.execute("SELECT c.value, tr.status, tr.translation_content, tr.context_hash FROM th_translations tr JOIN th_content c ON tr.content_id = c.id WHERE tr.lang_code = 'jp'")
            final_jp_statuses = {row['value']: (row['status'], row['translation_content'], row['context_hash']) for row in cursor.fetchall()}
            
            # 验证法语和德语任务
            cursor.execute("SELECT status FROM th_translations WHERE lang_code = 'fr'")
            final_fr_status = cursor.fetchone()['status']
            cursor.execute("SELECT status FROM th_translations WHERE lang_code = 'de'")
            final_de_status = cursor.fetchone()['status']

        print(f"  > 日语任务最终状态: {final_jp_statuses}")
        print(f"  > 法语任务最终状态: {final_fr_status}")
        print(f"  > 德语任务最终状态: {final_de_status}")
        
        # 断言
        banana_context_hash = get_context_hash(context_for_banana)
        assert final_jp_statuses['apple'][0] == TranslationStatus.TRANSLATED
        assert final_jp_statuses['apple'][1] == "elppa-jp"
        assert final_jp_statuses['banana'][0] == TranslationStatus.TRANSLATED
        assert final_jp_statuses['banana'][2] == banana_context_hash, "上下文哈希不匹配"
        
        assert final_fr_status == TranslationStatus.PENDING
        assert final_de_status == TranslationStatus.PENDING
        
        print("\n所有验证成功！Coordinator 的 request() 和 process() 流程工作正常！")

    finally:
        # --- 关闭资源 ---
        coordinator.close()

if __name__ == "__main__":
    main()
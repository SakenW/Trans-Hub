# main.py
import os
import sys

import structlog

# 导入 Trans-Hub 的核心组件
from dotenv import load_dotenv

from trans_hub.config import EngineConfigs, TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler

# 获取一个 logger
log = structlog.get_logger()


def initialize_trans_hub():
    """一个标准的初始化函数，返回一个配置好的 Coordinator 实例。"""
    setup_logging(log_level="INFO")

    DB_FILE = "my_translations.db"
    if not os.path.exists(DB_FILE):
        log.info("数据库不存在，正在创建并迁移...", db_path=DB_FILE)
        apply_migrations(DB_FILE)

    handler = DefaultPersistenceHandler(db_path=DB_FILE)

    # 创建一个最简单的配置对象，它将自动使用默认的免费 'translators' 引擎。
    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE}", engine_configs=EngineConfigs()
    )

    coordinator = Coordinator(config=config, persistence_handler=handler)
    return coordinator


def main():
    """主程序入口"""
    # 在程序最开始主动加载 .env 文件，这是一个健壮的实践
    load_dotenv()

    coordinator = initialize_trans_hub()
    try:
        text_to_translate = "Hello, world!"
        # 使用标准语言代码
        target_language_code = "zh-CN"

        # --- 使用 try...except 块来优雅地处理预期的错误 ---
        try:
            log.info("正在登记翻译任务", text=text_to_translate, lang=target_language_code)
            coordinator.request(
                target_langs=[target_language_code],
                text_content=text_to_translate,
                business_id="app.greeting.hello_world",
            )
        except ValueError as e:
            # 捕获我们自己定义的输入验证错误
            log.error(
                "无法登记翻译任务，输入参数有误。",
                reason=str(e),
                suggestion="请检查你的语言代码是否符合 'en' 或 'zh-CN' 这样的标准格式。",
            )
            # 优雅地退出
            sys.exit(1)

        # --- 执行翻译工作 ---
        log.info(f"正在处理 '{target_language_code}' 的待翻译任务...")
        results_generator = coordinator.process_pending_translations(
            target_lang=target_language_code
        )

        results = list(results_generator)

        if results:
            first_result = results[0]
            log.info(
                "翻译完成！",
                original=first_result.original_content,
                translation=first_result.translated_content,
                status=first_result.status,
                engine=first_result.engine,
            )
        else:
            log.warning("没有需要处理的新任务（可能已翻译过）。")

    except Exception:
        # 捕获所有其他意外的、严重的错误
        log.critical("程序运行中发生未知严重错误！", exc_info=True)
    finally:
        # 确保 coordinator 实例存在时才调用 close
        if "coordinator" in locals() and coordinator:
            coordinator.close()


if __name__ == "__main__":
    main()

# inspect_db.py (最终修正版)
# 标准库 logging 配置
import logging
import os
import sqlite3
import sys  # 导入 sys 模块，用于日志输出流
from datetime import datetime

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import (
    JSONRenderer,
    StackInfoRenderer,
    TimeStamper,
    format_exc_info,
)

# 导入 structlog 必要的处理器
from structlog.stdlib import add_log_level, add_logger_name

logging.basicConfig(level=logging.INFO, stream=sys.stdout)  # 将标准日志输出到控制台
logging.getLogger("pydantic").setLevel(logging.INFO)  # 避免 Pydantic 大量日志

# 配置 structlog
structlog.configure(
    processors=[
        add_logger_name,  # 确保 logger 名称显示
        add_log_level,  # 确保日志级别显示
        TimeStamper(fmt="%Y-%m-%dT%H:%M:%S.%fZ", utc=True),  # 添加时间戳
        StackInfoRenderer(),  # 捕获堆栈信息
        format_exc_info,  # 格式化异常信息
        # 根据环境变量选择渲染器，方便生产环境切换为 JSON
        ConsoleRenderer() if os.getenv("ENV") != "prod" else JSONRenderer(),
    ],
    # 配置 structlog 包装标准库的 logger
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
)

# 获取一个 logger
log = structlog.get_logger(__name__)  # 使用 __name__ 作为 logger 名称


# 数据库文件路径，与 context_demo.py 使用的保持一致
DB_FILE = "my_complex_trans_hub_demo.db"


def inspect_database():
    """连接到数据库并打印翻译内容及其解读。"""
    if not os.path.exists(DB_FILE):
        log.error(f"数据库文件 '{DB_FILE}' 不存在。请先运行 main.py 生成数据。")
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row  # 这样可以通过列名访问结果，例如 row['id']
        log.info(f"成功连接到数据库: {DB_FILE}")

        # SQL 查询：LEFT JOIN th_translations, th_content, th_sources
        # 使用 LEFT JOIN th_sources 是为了即使没有 business_id 也能获取到翻译记录
        query = """
        SELECT
            t.id AS translation_id,
            c.value AS original_content,
            t.lang_code AS target_language,
            t.context_hash AS context_hash,
            t.translation_content AS translated_text,
            t.status AS translation_status,
            t.engine AS translation_engine,
            t.engine_version AS engine_version,
            s.business_id AS business_id,
            s.last_seen_at AS source_last_seen_at
        FROM
            th_translations t
        JOIN
            th_content c ON t.content_id = c.id
        LEFT JOIN
            th_sources s ON c.id = s.content_id AND t.context_hash = s.context_hash;
        """

        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        print("\n" + "=" * 80)
        print("                 Trans-Hub 数据库翻译记录概览与解读")
        print("=" * 80 + "\n")

        if not rows:
            print("数据库中没有翻译记录。请运行 main.py 以生成数据。")
            return

        for i, row in enumerate(rows):
            print(f"--- 记录 {i+1} ---")
            print(f"原始数据库行内容 (sqlite3.Row 对象):")
            # 核心修正：使用 row.keys() 迭代列名，然后通过键访问值
            for key in row.keys():  # <-- 修正点：使用 .keys()
                print(f"  {key}: {row[key]}")  # <-- 修正点：通过键访问值

            print("\n解读:")
            print(f"  翻译任务ID (translation_id): {row['translation_id']}")
            print(f"    - 这是该翻译任务在 `th_translations` 表中的唯一标识。")
            print(f"  原始文本 (original_content): '{row['original_content']}'")
            print(f"    - 该文本是所有翻译的源头，存储在 `th_content` 表中，保证了文本内容的唯一性。")
            print(f"  目标语言 (target_language): '{row['target_language']}'")
            print(f"    - 原始文本被翻译成的目标语言代码，遵循 IETF 语言标签（如 'zh-CN', 'fr'）。")
            print(f"  上下文哈希 (context_hash): '{row['context_hash']}'")
            print(f"    - 如果文本在不同场景下有不同译法，这里会是上下文的哈希值。`__GLOBAL__` 表示无特定上下文。")
            print(
                f"  翻译结果 (translated_text): '{row['translated_text'] if row['translated_text'] else '暂无翻译结果'}'"
            )
            print(f"    - 翻译引擎返回的最终译文。如果任务状态不是 'TRANSLATED'，则可能为 `None`。")
            print(f"  翻译状态 (translation_status): '{row['translation_status']}'")
            print(
                f"    - 翻译任务的当前生命周期状态：\n      - `PENDING`: 待处理，等待翻译引擎拾取。\n      - `TRANSLATING`: 正在处理，已提交给引擎。\n      - `TRANSLATED`: 已成功翻译。\n      - `FAILED`: 翻译失败且重试次数耗尽。\n      - `APPROVED`: 人工审核通过的最终版本。"
            )
            print(f"  翻译引擎 (translation_engine): '{row['translation_engine']}'")
            print(f"    - 执行此次翻译的引擎名称（例如 'translators', 'openai'）。")
            print(f"  引擎版本 (engine_version): '{row['engine_version']}'")
            print(f"    - 使用的翻译引擎的具体版本号。")

            business_id = row["business_id"]
            if business_id:
                print(f"  业务标识符 (business_id): '{business_id}'")
                print(f"    - 上层应用定义的唯一业务ID，用于追踪此翻译在业务中的位置，存储在 `th_sources` 表。")
                print(
                    f"  来源最后活跃时间 (source_last_seen_at): '{row['source_last_seen_at']}'"
                )
                print(
                    f"    - 此 `business_id` 最后一次被 `request()` 方法访问或更新的时间，用于垃圾回收 (GC)。"
                )
            else:
                print(f"  业务标识符 (business_id): 无 (此翻译未关联业务ID，或其 `th_sources` 记录已被GC。)")
                print(
                    f"    - 原始请求可能没有提供 `business_id`，或者此翻译是即席翻译而没有关联 `business_id`，或者在 `th_sources` 表中对应的记录已被垃圾回收清理。"
                )

            print("\n" + "-" * 80 + "\n")

    except sqlite3.Error as e:
        log.critical(f"数据库操作失败: {e}", exc_info=True)
    except Exception as e:
        log.critical(f"程序运行中发生未知错误: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()
            log.info("数据库连接已关闭。")


if __name__ == "__main__":
    inspect_database()

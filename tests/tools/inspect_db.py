# tools/inspect_db.py (最终修正版 - Ruff 清理后)
import logging
import os
import sqlite3
import sys
from pathlib import Path

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import (
    JSONRenderer,
    StackInfoRenderer,
    TimeStamper,
    format_exc_info,
)

# ==============================================================================
#  日志配置
# ==============================================================================
from structlog.stdlib import add_log_level, add_logger_name

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logging.getLogger("pydantic").setLevel(logging.INFO)
structlog.configure(
    processors=[
        add_logger_name,
        add_log_level,
        TimeStamper(fmt="%Y-%m-%dT%H:%M:%S.%fZ", utc=True),
        StackInfoRenderer(),
        format_exc_info,
        ConsoleRenderer() if os.getenv("ENV") != "prod" else JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
)
log = structlog.get_logger(__name__)
# ==============================================================================


def find_project_root() -> Path:
    """从当前脚本位置向上查找项目根目录（包含 pyproject.toml 的目录）。"""
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if (parent / "pyproject.toml").exists():
            log.debug("项目根目录已找到。", root_path=str(parent))
            return parent
    raise FileNotFoundError(
        "无法找到项目根目录 (pyproject.toml 文件未找到)。请确保从项目内部运行此脚本。"
    )


# --- 动态构建数据库文件路径 ---
try:
    PROJECT_ROOT = find_project_root()
    DB_FILE = PROJECT_ROOT / "my_complex_trans_hub_demo.db"
except FileNotFoundError as e:
    log.error(str(e))
    sys.exit(1)


def inspect_database():
    """连接到数据库并打印翻译内容及其解读。"""
    if not DB_FILE.exists():
        log.error(
            f"数据库文件 '{DB_FILE}' 不存在。",
            suggestion="请先从项目根目录运行 `poetry run python demo_complex_workflow.py` 来生成演示数据。",
        )
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        log.info(f"成功连接到数据库: {DB_FILE}")

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
            print("数据库中没有翻译记录。请运行 demo_complex_workflow.py 以生成数据。")
            return

        for i, row in enumerate(rows):
            print(f"--- 记录 {i+1} ---")
            print("原始数据库行内容 (sqlite3.Row 对象):")
            for key in row.keys():
                print(f"  {key}: {row[key]}")

            print("\n解读:")
            # --- 核心修正：移除所有不必要的 f-string ---
            print(f"  翻译任务ID (translation_id): {row['translation_id']}")
            print("    - 这是该翻译任务在 `th_translations` 表中的唯一标识。")
            print(f"  原始文本 (original_content): '{row['original_content']}'")
            print(
                "    - 该文本是所有翻译的源头，存储在 `th_content` 表中，保证了文本内容的唯一性。"
            )
            print(f"  目标语言 (target_language): '{row['target_language']}'")
            print(
                "    - 原始文本被翻译成的目标语言代码，遵循 IETF 语言标签（如 'zh-CN', 'fr'）。"
            )
            print(f"  上下文哈希 (context_hash): '{row['context_hash']}'")
            print(
                "    - 如果文本在不同场景下有不同译法，这里会是上下文的哈希值。`__GLOBAL__` 表示无特定上下文。"
            )
            print(
                f"  翻译结果 (translated_text): '{row['translated_text'] if row['translated_text'] else '暂无翻译结果'}'"
            )
            print(
                "    - 翻译引擎返回的最终译文。如果任务状态不是 'TRANSLATED'，则可能为 `None`。"
            )
            print(f"  翻译状态 (translation_status): '{row['translation_status']}'")
            print(
                "    - 翻译任务的当前生命周期状态：\n      - `PENDING`: 待处理，等待翻译引擎拾取。\n      - `TRANSLATING`: 正在处理，已提交给引擎。\n      - `TRANSLATED`: 已成功翻译。\n      - `FAILED`: 翻译失败且重试次数耗尽。\n      - `APPROVED`: 人工审核通过的最终版本。"
            )
            print(f"  翻译引擎 (translation_engine): '{row['translation_engine']}'")
            print("    - 执行此次翻译的引擎名称（例如 'translators', 'openai'）。")
            print(f"  引擎版本 (engine_version): '{row['engine_version']}'")
            print("    - 使用的翻译引擎的具体版本号。")

            business_id = row["business_id"]
            if business_id:
                print(f"  业务标识符 (business_id): '{business_id}'")
                print(
                    "    - 上层应用定义的唯一业务ID，用于追踪此翻译在业务中的位置，存储在 `th_sources` 表。"
                )
                print(
                    f"  来源最后活跃时间 (source_last_seen_at): '{row['source_last_seen_at']}'"
                )
                print(
                    "    - 此 `business_id` 最后一次被 `request()` 方法访问或更新的时间，用于垃圾回收 (GC)。"
                )
            else:
                print(
                    "  业务标识符 (business_id): 无 (此翻译未关联业务ID，或其 `th_sources` 记录已被GC。)"
                )
                print(
                    "    - 原始请求可能没有提供 `business_id`，或者此翻译是即席翻译而没有关联 `business_id`，或者在 `th_sources` 表中对应的记录已被垃圾回收清理。"
                )

            print("\n" + "=" * 80 + "\n")

    except sqlite3.Error as e:
        log.critical(f"数据库操作失败: {e}", exc_info=True)
    except Exception:
        log.critical("程序运行中发生未知错误！", exc_info=True)
    finally:
        if conn:
            conn.close()
            log.info("数据库连接已关闭。")


if __name__ == "__main__":
    inspect_database()

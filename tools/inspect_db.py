# tools/inspect_db.py (终极完整版)
"""
一个专业的命令行工具，用于检查和解读 Trans-Hub 数据库的内容。

使用方法:
 poetry run python tools/inspect_db.py /path/to/your/database.db
 poetry run python tools/inspect_db.py examples/complex_demo.db
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# --- 核心修正：确保脚本在任何位置都能正确导入 trans_hub 模块 ---
try:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.append(str(project_root))
    from trans_hub.logging_config import setup_logging
except (ImportError, IndexError):
    print("错误: 无法将项目根目录添加到 sys.path。请确保此脚本位于 'tools' 目录下。")
    sys.exit(1)
# -------------------------------------------------------------------

import aiosqlite
import structlog

log = structlog.get_logger(__name__)


async def inspect_database(db_path: str):
    """异步地连接到数据库并打印翻译内容及其解读。"""
    if not os.path.exists(db_path):
        log.error(
            "数据库文件不存在。",
            path=db_path,
            suggestion="请提供一个有效的数据库文件路径。",
        )
        return

    conn = None
    try:
        conn = await aiosqlite.connect(db_path)
        conn.row_factory = aiosqlite.Row
        log.info("✅ 成功连接到数据库", path=db_path)

        query = """
        SELECT
            t.id AS translation_id, c.value AS original_content, t.lang_code,
            t.context_hash, t.translation_content, t.status, t.engine, t.engine_version,
            s.business_id, s.last_seen_at
        FROM th_translations t
        JOIN th_content c ON t.content_id = c.id
        LEFT JOIN th_sources s ON c.id = s.content_id AND t.context_hash = s.context_hash
        ORDER BY t.id;
        """

        cursor = await conn.cursor()
        await cursor.execute(query)
        # --- 核心修正：将 fetchall() 的结果显式转换为 list ---
        rows: list[aiosqlite.Row] = list(await cursor.fetchall())

        print("\n" + "=" * 80)
        print("                 Trans-Hub 数据库翻译记录概览")
        print("=" * 80 + "\n")

        if not rows:
            print("数据库中没有翻译记录。")
            return

        for i, row in enumerate(rows):
            print(f"--- 记录 {i + 1} ---")
            for key in row.keys():
                print(f"  - {key:<20}: {row[key]}")

            print("\n  **解读**:")
            print(
                f"    此任务 (ID: {row['translation_id']}) 是将文本 '{row['original_content']}' 翻译成 '{row['lang_code']}'。"
            )
            print(
                f"    当前状态为 '{row['status']}'，由 '{row['engine']}' (版本: {row['engine_version']}) 处理。"
            )
            if row["business_id"]:
                print(
                    f"    它与业务ID '{row['business_id']}' 相关联，该关联的最后活跃时间是 {row['last_seen_at']}。"
                )
            else:
                print("    此翻译任务没有关联任何活跃的业务ID。")

            print("\n" + ("-" * 40 if i < len(rows) - 1 else "=" * 80) + "\n")

    except aiosqlite.Error as e:
        log.critical("数据库操作失败", error=e, exc_info=True)
    finally:
        if conn:
            await conn.close()
            log.info("数据库连接已关闭。")


def main():
    """命令行接口的主入口点。"""
    setup_logging(log_level="INFO")

    parser = argparse.ArgumentParser(
        description="一个用于检查和解读 Trans-Hub 数据库内容的工具。",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "db_path",
        type=str,
        help="要检查的 Trans-Hub SQLite 数据库文件的路径。\n"
        "例如: poetry run python tools/inspect_db.py examples/complex_demo.db",
    )

    args = parser.parse_args()
    asyncio.run(inspect_database(args.db_path))


if __name__ == "__main__":
    main()

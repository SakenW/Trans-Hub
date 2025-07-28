# trans_hub/db/schema_manager.py
"""
本模块负责管理数据库的 Schema 版本。
它提供了应用迁移脚本、检查当前版本等功能。
"""

import sqlite3
from pathlib import Path
from typing import Union

import structlog

logger = structlog.get_logger(__name__)

# 定义迁移脚本所在的目录
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_current_schema_version(conn: sqlite3.Connection) -> int:
    """
    查询数据库中当前的 schema 版本。

    返回当前 schema 版本号，如果元数据表或版本记录不存在，则返回 0。
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='th_meta'"
        )
        if cursor.fetchone() is None:
            return 0

        cursor.execute("SELECT value FROM th_meta WHERE key = 'schema_version'")
        result = cursor.fetchone()
        return int(result[0]) if result else 0
    except sqlite3.Error as e:
        logger.error("查询 schema 版本时出错", error=e)
        return -1


def apply_migrations(db_source: Union[str, sqlite3.Connection]) -> None:
    """
    连接到指定的 SQLite 数据库，并按顺序应用所有必要的迁移脚本。

    参数:
        db_source: 可以是数据库文件路径字符串，或一个已存在的 sqlite3.Connection 对象。
    """
    logger.info("开始对数据库进行迁移...", db_source_type=type(db_source).__name__)

    conn: sqlite3.Connection
    if isinstance(db_source, str):
        # 如果是路径，创建新连接
        try:
            conn = sqlite3.connect(db_source, timeout=10.0)
            close_conn_after = True
        except sqlite3.Error as e:
            logger.error("数据库连接过程中发生错误", path=db_source, error=e)
            raise
    else:
        # 如果是已存在的连接，直接使用
        conn = db_source
        close_conn_after = False

    try:
        current_version = get_current_schema_version(conn)
        if current_version == -1:
            logger.error("无法确定数据库版本，迁移中止。")
            return

        logger.info("当前数据库 schema 版本", version=current_version)

        migration_files = sorted(
            MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"),
            key=lambda f: int(f.name.split("_")[0]),
        )

        applied_count = 0
        for migration_file in migration_files:
            version = int(migration_file.name.split("_")[0])
            if version > current_version:
                logger.info("正在应用迁移脚本...", script=migration_file.name)
                try:
                    sql_script = migration_file.read_text("utf-8")
                    conn.executescript(sql_script)
                    conn.commit()
                    logger.info("✅ 成功应用迁移", version=version)
                    applied_count += 1
                except sqlite3.Error as e:
                    logger.error(
                        "应用迁移失败，正在回滚...",
                        script=migration_file.name,
                        error=e,
                    )
                    conn.rollback()
                    raise

        if applied_count == 0:
            logger.info("数据库 schema 已是最新，无需迁移。")
        else:
            final_version = get_current_schema_version(conn)
            logger.info(
                "🎉 迁移完成。数据库 schema 版本已更新至",
                final_version=final_version,
            )
    finally:
        if close_conn_after:
            conn.close()


if __name__ == "__main__":
    from trans_hub.logging_config import setup_logging

    setup_logging(log_level="INFO")
    test_db_path = "transhub_cli_test.db"
    print(f"\n正在对测试数据库 '{test_db_path}' 应用迁移...")
    apply_migrations(test_db_path)
    print("\n操作完成。")

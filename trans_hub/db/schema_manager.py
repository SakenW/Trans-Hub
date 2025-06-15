"""trans_hub/db/schema_manager.py

本模块负责管理数据库的 Schema 版本。
它提供了应用迁移脚本、检查当前版本等功能。
"""

import logging
import sqlite3
from pathlib import Path

import structlog

# 设置一个简单的日志记录器
logger = structlog.get_logger(__name__)

# 定义迁移脚本所在的目录
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_current_schema_version(conn: sqlite3.Connection) -> int:
    """查询数据库中当前的 schema 版本。

    Args:
    ----
        conn: 一个已连接的 sqlite3.Connection 对象。

    Returns:
    -------
        返回当前的 schema 版本号。如果元数据表不存在或版本记录不存在，
        则返回 0，表示数据库是全新的或处于未知状态。

    """
    cursor = conn.cursor()
    try:
        # 检查 th_meta 表是否存在
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='th_meta'"
        )
        if cursor.fetchone() is None:
            return 0  # 表不存在，认为是版本 0

        # 查询版本号
        cursor.execute("SELECT value FROM th_meta WHERE key = 'schema_version'")
        result = cursor.fetchone()
        if result:
            return int(result[0])
        else:
            return 0  # 表存在但没有版本记录，也认为是版本 0
    except sqlite3.Error as e:
        logger.error(f"查询 schema 版本时出错: {e}")
        return -1  # 表示查询出错


def apply_migrations(db_path: str) -> None:
    """连接到指定的 SQLite 数据库，并应用所有必要的迁移脚本。

    此函数会：
    1. 连接数据库。
    2. 检查当前 schema 版本。
    3. 按顺序查找并应用所有比当前版本号更高的迁移脚本。

    Args:
    ----
        db_path: SQLite 数据库文件的路径。

    """
    logger.info(f"开始对数据库 '{db_path}' 进行迁移...")

    try:
        # 使用 with 语句确保连接被安全关闭
        with sqlite3.connect(db_path) as conn:
            # 必须在事务外执行，确保立即生效
            conn.execute("PRAGMA foreign_keys = ON;")

            current_version = get_current_schema_version(conn)
            if current_version == -1:
                logger.error("无法确定数据库版本，迁移中止。")
                return

            logger.info(f"当前数据库 schema 版本: {current_version}")

            # 查找所有迁移文件，并按版本号排序
            migration_files = sorted(
                MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"),
                key=lambda f: int(f.name.split("_")[0]),
            )

            applied_count = 0
            for migration_file in migration_files:
                version = int(migration_file.name.split("_")[0])
                if version > current_version:
                    logger.info(f"应用迁移脚本: {migration_file.name}")
                    try:
                        sql_script = migration_file.read_text("utf-8")
                        # 使用 executescript 来执行包含多个语句的 SQL 文件
                        conn.executescript(sql_script)
                        conn.commit()
                        logger.info(f"成功应用版本 {version} 的迁移。")
                        applied_count += 1
                    except sqlite3.Error as e:
                        logger.error(f"应用迁移 {migration_file.name} 时失败: {e}")
                        conn.rollback()  # 如果失败，回滚事务
                        # 迁移失败是严重问题，应立即中止
                        raise

            if applied_count == 0:
                logger.info("数据库 schema 已是最新，无需迁移。")
            else:
                final_version = get_current_schema_version(conn)
                logger.info(f"迁移完成。数据库 schema 版本已更新至: {final_version}")

    except sqlite3.Error as e:
        logger.error(f"数据库连接或迁移过程中发生错误: {e}")
        raise  # 将异常向上抛出，让调用者知道操作失败


if __name__ == "__main__":
    # 这是一个简单的命令行调用示例，用于手动执行迁移
    # 使用方法: python -m trans_hub.db.schema_manager
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # 在项目根目录下创建一个名为 'transhub.db' 的数据库文件用于测试
    test_db_path = "transhub.db"
    print(f"正在对测试数据库 '{test_db_path}' 应用迁移...")
    apply_migrations(test_db_path)
    print("操作完成。")

# tools/clear_database.py
"""一个用于删除 Trans-Hub 数据库所有表的工具脚本。"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

try:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from trans_hub.logging_config import setup_logging  # noqa: E402
except (ImportError, IndexError):
    print("错误: 无法将项目根目录添加到 sys.path。请确保此脚本位于 'tools' 目录下。")
    sys.exit(1)

import aiosqlite  # noqa: E402
import structlog  # noqa: E402

from trans_hub.config import TransHubConfig  # noqa: E402

log = structlog.get_logger(__name__)


class DatabaseClearer:
    """封装了删除 Trans-Hub 数据库所有表的逻辑的类。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: aiosqlite.Connection | None = None

    async def clear(self) -> None:
        """执行数据库表删除的主流程。"""
        if not os.path.exists(self.db_path):
            log.error("数据库文件不存在。", path=self.db_path)
            return

        try:
            self.conn = await aiosqlite.connect(self.db_path)
            self.conn.row_factory = aiosqlite.Row
            log.info("✅ 成功连接到数据库", path=self.db_path)
            
            # 禁用外键约束以避免删除顺序问题
            await self.conn.execute("PRAGMA foreign_keys = OFF;")
            
            # 删除所有表
            tables = [
                "th_projects",
                "th_content",
                "th_trans_rev",
                "th_trans_head",
                "search_content",
                "th_tm",
                "th_tm_links",
                "th_locales_fallbacks",
                "th_resolve_cache",
            ]
            
            # 反向删除表以避免外键约束问题
            for table in reversed(tables):
                try:
                    await self.conn.execute(f"DROP TABLE IF EXISTS {table};")
                    log.info(f"✅ 已删除表 {table}")
                except aiosqlite.OperationalError as e:
                    log.warning(f"⚠️  表 {table} 无法删除: {e}")
            
            # 重新启用外键约束
            await self.conn.execute("PRAGMA foreign_keys = ON;")
            
            # 提交事务
            await self.conn.commit()
            log.info("✅ 数据库表删除完成")
        finally:
            if self.conn:
                await self.conn.close()
                log.info("数据库连接已关闭。")


def main() -> None:
    """命令行接口的主入口点。"""
    setup_logging(log_level="INFO")
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="一个用于删除 Trans-Hub 数据库所有表的工具脚本。",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="环境配置文件路径，默认为项目根目录下的 .env 文件。",
    )
    
    args = parser.parse_args()
    
    # 加载配置
    config = TransHubConfig(_env_file=args.env_file)
    
    # 创建并运行清空器
    try:
        clearer = DatabaseClearer(config.db_path)
        asyncio.run(clearer.clear())
    except Exception:
        log.exception("执行过程中发生意外错误：")
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("操作被用户中断。")
        sys.exit(0)


if __name__ == "__main__":
    main()
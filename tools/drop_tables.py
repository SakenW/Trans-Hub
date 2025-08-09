# tools/drop_tables.py
"""一个用于删除 Trans-Hub PostgreSQL 数据库所有表的工具脚本。"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import structlog

# 添加项目根目录到 Python 路径，使 trans_hub 模块可导入
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from trans_hub.config import TransHubConfig  # noqa: E402

try:
    import asyncpg
except ImportError:
    asyncpg = None

log = structlog.get_logger(__name__)


class PostgresTableDropper:
    """封装了删除 Trans-Hub PostgreSQL 数据库所有表的逻辑的类。"""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.conn: asyncpg.Connection | None = None

    async def connect(self) -> None:
        """建立数据库连接。"""
        if asyncpg is None:
            raise RuntimeError("未安装 asyncpg 库，请通过 poetry install -E postgres 安装可选依赖。")
        # 转换 DSN 以兼容 asyncpg
        connect_dsn = self.dsn.replace("postgresql+asyncpg", "postgresql", 1)
        self.conn = await asyncpg.connect(dsn=connect_dsn)
        log.info("✅ 已连接到 PostgreSQL 数据库")

    async def close(self) -> None:
        """关闭数据库连接。"""
        if self.conn and not self.conn.is_closed():
            await self.conn.close()
            log.info("🔒 数据库连接已关闭")

    async def drop_all_tables(self) -> None:
        """执行数据库表删除的主流程。"""
        if not self.conn:
            raise RuntimeError("数据库未连接。")

        try:
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
                    await self.conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                    log.info(f"✅ 已删除表 {table}")
                except Exception as e:
                    log.warning(f"⚠️  表 {table} 无法删除: {e}")
            
            log.info("✅ PostgreSQL 数据库表删除完成")
        except Exception as e:
            log.error("❌ 删除数据库表时发生错误", exc_info=True)
            raise
        finally:
            await self.close()


async def main() -> None:
    """主函数，处理命令行参数并执行数据库表删除。"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="一个用于删除 Trans-Hub PostgreSQL 数据库所有表的工具脚本。",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="指定 .env 配置文件路径 (默认: .env)"
    )
    args = parser.parse_args()

    # 加载配置
    config = TransHubConfig(_env_file=args.env_file)
    
    # 检查数据库类型
    if not config.database_url.startswith("postgresql"):
        log.error("❌ 仅支持 PostgreSQL 数据库，请检查配置文件中的 database_url。")
        sys.exit(1)
    
    # 创建数据库表删除器
    dropper = PostgresTableDropper(config.database_url)
    
    try:
        # 连接数据库
        await dropper.connect()
        
        # 删除所有表
        await dropper.drop_all_tables()
        
        log.info("🎉 所有表已成功删除！")
    except Exception as e:
        log.error("❌ 删除表失败", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
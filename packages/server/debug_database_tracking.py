#!/usr/bin/env python3
# packages/server/debug_database_tracking.py
"""
详细追踪数据库连接和迁移过程的调试脚本
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
from trans_hub.bootstrap.init import create_app_config
from trans_hub.infrastructure.db.engine import create_async_db_engine


def print_step(step: str, details: str = "") -> None:
    """打印步骤信息"""
    print(f"\n{'='*60}")
    print(f"步骤: {step}")
    if details:
        print(f"详情: {details}")
    print(f"{'='*60}")


def print_db_info(title: str, url: str) -> None:
    """打印数据库信息"""
    print(f"\n{title}:")
    print(f"  完整URL: {url}")
    
    # 解析URL组件
    if "://" in url:
        scheme, rest = url.split("://", 1)
        print(f"  协议: {scheme}")
        
        if "@" in rest:
            auth, host_db = rest.split("@", 1)
            print(f"  认证: {auth}")
        else:
            host_db = rest
            
        if "/" in host_db:
            host_port, db_name = host_db.rsplit("/", 1)
            print(f"  主机:端口: {host_port}")
            print(f"  数据库名: {db_name}")
        else:
            print(f"  主机:端口: {host_db}")
            print(f"  数据库名: (未指定)")


async def check_database_content(engine: Any, title: str, is_sqlite: bool = False) -> None:
    """检查数据库内容"""
    print(f"\n--- {title} 数据库内容检查 ---")
    
    try:
        async with engine.begin() as conn:
            # 根据数据库类型使用不同的查询
            if is_sqlite:
                # SQLite使用sqlite_master表
                result = await conn.execute(text("""
                    SELECT 'main' as table_schema, name as table_name 
                    FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                """))
            else:
                # PostgreSQL使用information_schema
                result = await conn.execute(text("""
                    SELECT table_schema, table_name 
                    FROM information_schema.tables 
                    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
                    ORDER BY table_schema, table_name
                """))
            
            tables = result.fetchall()
            
            print(f"找到 {len(tables)} 个表:")
            for schema, table in tables:
                if is_sqlite:
                    table_ref = table  # SQLite不使用schema前缀
                    print(f"  {table}")
                else:
                    table_ref = f"{schema}.{table}"
                    print(f"  {schema}.{table}")
                
                # 检查表的行数
                count_result = await conn.execute(text(f"SELECT COUNT(*) FROM {table_ref}"))
                count = count_result.scalar()
                print(f"    行数: {count}")
                
                # 如果是alembic_version表，显示详细内容
                if table == "alembic_version":
                    version_result = await conn.execute(text(f"SELECT * FROM {table_ref}"))
                    versions = version_result.fetchall()
                    print(f"    版本记录: {versions}")
                    
    except Exception as e:
        print(f"检查数据库内容时出错: {e}")


def check_sync_database_content(engine: Any, title: str, is_sqlite: bool = False) -> None:
    """检查同步数据库内容"""
    print(f"\n--- {title} 数据库内容检查 (同步) ---")
    
    try:
        with engine.begin() as conn:
            # 根据数据库类型使用不同的查询
            if is_sqlite:
                # SQLite使用sqlite_master表
                result = conn.execute(text("""
                    SELECT 'main' as table_schema, name as table_name 
                    FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                """))
            else:
                # PostgreSQL使用information_schema
                result = conn.execute(text("""
                    SELECT table_schema, table_name 
                    FROM information_schema.tables 
                    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
                    ORDER BY table_schema, table_name
                """))
            
            tables = result.fetchall()
            
            print(f"找到 {len(tables)} 个表:")
            for schema, table in tables:
                if is_sqlite:
                    table_ref = table  # SQLite不使用schema前缀
                    print(f"  {table}")
                else:
                    table_ref = f"{schema}.{table}"
                    print(f"  {schema}.{table}")
                
                # 检查表的行数
                count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_ref}"))
                count = count_result.scalar()
                print(f"    行数: {count}")
                
                # 如果是alembic_version表，显示详细内容
                if table == "alembic_version":
                    version_result = conn.execute(text(f"SELECT * FROM {table_ref}"))
                    versions = version_result.fetchall()
                    print(f"    版本记录: {versions}")
                    
    except Exception as e:
        print(f"检查数据库内容时出错: {e}")


async def main() -> None:
    """主函数"""
    print("开始数据库连接和迁移过程追踪")
    
    # 步骤1: 加载配置
    print_step("1", "加载应用配置")
    config = create_app_config("dev")
    print(f"应用环境: {config.app_env}")
    print(f"数据库配置: {config.database}")
    
    # 步骤2: 显示原始数据库URL
    print_step("2", "显示原始数据库连接信息")
    original_db_url = config.database.url
    print_db_info("原始数据库URL", original_db_url)
    
    # 步骤3: 创建临时数据库URL
    print_step("3", "创建临时测试数据库")
    import uuid
    temp_db_name = f"test_transhub_{uuid.uuid4().hex[:8]}"
    
    # 解析原始URL并替换数据库名
    if original_db_url.endswith("/transhub"):
        temp_db_url = original_db_url.rsplit("/", 1)[0] + f"/{temp_db_name}"
    else:
        temp_db_url = f"{original_db_url}_{temp_db_name}"
    
    print_db_info("临时数据库URL", temp_db_url)
    
    # 步骤4: 处理数据库创建（根据数据库类型）
    print_step("4", "处理临时数据库创建")
    
    is_sqlite = original_db_url.startswith("sqlite")
    
    if is_sqlite:
        print("检测到SQLite数据库，无需预先创建数据库文件")
        print(f"SQLite文件将在首次连接时自动创建: {temp_db_url}")
    else:
        # PostgreSQL需要预先创建数据库
        postgres_url = original_db_url.rsplit("/", 1)[0] + "/postgres"
        print_db_info("管理数据库URL (用于创建临时数据库)", postgres_url)
        
        admin_engine = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
        
        try:
            async with admin_engine.begin() as conn:
                await conn.execute(text(f"CREATE DATABASE {temp_db_name}"))
                print(f"✓ 成功创建临时数据库: {temp_db_name}")
        except Exception as e:
            print(f"✗ 创建临时数据库失败: {e}")
            return
        finally:
            await admin_engine.dispose()
    
    # 步骤5: 连接到临时数据库并检查初始状态
    print_step("5", "连接到临时数据库并检查初始状态")
    temp_engine = create_async_engine(temp_db_url)
    
    try:
        await check_database_content(temp_engine, "临时数据库 (迁移前)", is_sqlite)
        
        # 步骤6: 设置Alembic配置
        print_step("6", "配置Alembic迁移")
        
        # 临时修改环境变量
        original_db_env = os.environ.get("TRANSHUB_DATABASE_URL")
        os.environ["TRANSHUB_DATABASE_URL"] = temp_db_url
        
        print(f"设置环境变量 TRANSHUB_DATABASE_URL = {temp_db_url}")
        
        # 创建Alembic配置
        alembic_cfg = Config("alembic.ini")
        print(f"Alembic配置文件: alembic.ini")
        print(f"Alembic脚本位置: {alembic_cfg.get_main_option('script_location')}")
        
        # 步骤7: 执行迁移
        print_step("7", "执行Alembic迁移")
        
        # 创建同步引擎用于Alembic
        if is_sqlite:
            sync_temp_url = temp_db_url.replace("sqlite+aiosqlite://", "sqlite://")
        else:
            sync_temp_url = temp_db_url.replace("postgresql+asyncpg://", "postgresql://")
        print_db_info("Alembic使用的同步数据库URL", sync_temp_url)
        
        sync_engine = create_engine(sync_temp_url)
        
        try:
            # 检查迁移前的数据库状态
            check_sync_database_content(sync_engine, "迁移前", is_sqlite)
            
            # 执行迁移
            print("\n开始执行迁移...")
            command.upgrade(alembic_cfg, "head")
            print("✓ 迁移执行完成")
            
            # 检查迁移后的数据库状态
            check_sync_database_content(sync_engine, "迁移后", is_sqlite)
            
        finally:
            sync_engine.dispose()
        
        # 步骤8: 使用异步引擎再次检查
        print_step("8", "使用异步引擎检查迁移结果")
        await check_database_content(temp_engine, "临时数据库 (迁移后)", is_sqlite)
        
        # 步骤9: 检查Alembic历史
        print_step("9", "检查Alembic迁移历史")
        try:
            print("\nAlembic当前版本:")
            command.current(alembic_cfg, verbose=True)
            
            print("\nAlembic迁移历史:")
            command.history(alembic_cfg, verbose=True)
        except Exception as e:
            print(f"检查Alembic历史时出错: {e}")
        
        # 恢复环境变量
        if original_db_env:
            os.environ["TRANSHUB_DATABASE_URL"] = original_db_env
        else:
            os.environ.pop("TRANSHUB_DATABASE_URL", None)
            
    finally:
        await temp_engine.dispose()
        
        # 步骤10: 清理临时数据库
        print_step("10", "清理临时数据库")
        
        if is_sqlite:
             # SQLite: 直接删除文件
            db_file = temp_db_url.replace("sqlite+aiosqlite:///", "")
            try:
                if os.path.exists(db_file):
                    os.remove(db_file)
                    print(f"✓ 成功删除SQLite文件: {db_file}")
                else:
                    print(f"SQLite文件不存在，无需删除: {db_file}")
            except Exception as e:
                print(f"✗ 删除SQLite文件失败: {e}")
        else:
            # PostgreSQL: 删除数据库
            admin_engine = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
            
            try:
                async with admin_engine.begin() as conn:
                    # 强制断开所有连接
                    await conn.execute(text(f"""
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = '{temp_db_name}' AND pid <> pg_backend_pid()
                    """))
                    
                    await conn.execute(text(f"DROP DATABASE {temp_db_name}"))
                    print(f"✓ 成功删除临时数据库: {temp_db_name}")
            except Exception as e:
                print(f"✗ 删除临时数据库失败: {e}")
            finally:
                await admin_engine.dispose()
    
    print("\n数据库连接和迁移过程追踪完成")


if __name__ == "__main__":
    asyncio.run(main())
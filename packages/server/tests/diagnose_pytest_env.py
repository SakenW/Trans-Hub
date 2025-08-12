# packages/server/tests/diagnose_pytest_env.py
"""
一个专门的诊断测试程序，用于逐层排查在 pytest 环境下数据库连接失败的根本原因。
(v2 - 直接注入连接到 Alembic)
"""
import asyncio
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine as create_sync_engine, text
from sqlalchemy.engine.url import make_url

# 确保能导入项目代码
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# 使用与 conftest.py 完全相同的 config fixture
from tests.conftest import config

pytestmark = pytest.mark.asyncio

@pytest.mark.asyncio
async def test_diagnostic_flow(config):
    """
    一个集成的诊断流程，按顺序执行所有关键步骤。
    """
    print("\n" + "="*80)
    print(" " * 25 + "开始终极诊断流程")
    print("="*80)

    maint_url = make_url(config.maintenance_database_url)
    app_url = make_url(config.database_url)
    test_db_name = f"test_diag_{uuid.uuid4().hex[:8]}"
    
    sync_maint_engine = None
    
    try:
        # --- 第一步: 连接到维护库 ---
        print("\n" + "-"*30 + " 第一步: 连接维护库 " + "-"*30)
        sync_maint_url = maint_url.set(drivername="postgresql+psycopg")
        sync_maint_engine = create_sync_engine(sync_maint_url, isolation_level="AUTOCOMMIT")
        with sync_maint_engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1
        print("✅ [成功] 第一步：成功连接到维护库。")

        # --- 第二步: 创建临时数据库 ---
        print("\n" + "-"*30 + " 第二步: 创建临时库 " + "-"*30)
        with sync_maint_engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS \"{test_db_name}\" WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE \"{test_db_name}\""))
        print(f"✅ [成功] 第二步：成功创建临时数据库 '{test_db_name}'。")

        # --- 第三步: 在临时数据库上运行 Alembic (新方法) ---
        print("\n" + "-"*23 + " 第三步: 在临时库上直接注入连接并迁移 " + "-"*23)
        from alembic import command
        from alembic.config import Config as AlembicConfig
        from alembic.runtime.environment import EnvironmentContext
        from alembic.script import ScriptDirectory

        server_root = Path(__file__).parent.parent
        alembic_cfg = AlembicConfig()
        alembic_cfg.set_main_option("script_location", str(server_root / "alembic"))
        
        sync_test_url = app_url.set(database=test_db_name, drivername="postgresql+psycopg")
        
        # [核心修复] 我们自己创建引擎并建立连接
        connectable = create_sync_engine(sync_test_url)
        with connectable.connect() as connection:
            print(f"[*] 已成功建立到 '{test_db_name}' 的连接，现在将此连接传递给 Alembic。")
            
            # 将连接注入 Alembic 的上下文
            alembic_cfg.attributes['connection'] = connection
            
            # 直接运行迁移命令
            command.upgrade(alembic_cfg, "head")

        print("✅ [成功] 第三步：Alembic 迁移成功。")

    except Exception as e:
        print(f"❌ [失败] 诊断在当前步骤中断！")
        pytest.fail(f"诊断失败: {e}", pytrace=True)

    finally:
        # --- 清理 ---
        print("\n" + "-"*35 + " 清理 " + "-"*35)
        if sync_maint_engine:
            with sync_maint_engine.connect() as conn:
                print(f"[*] 正在删除临时数据库: {test_db_name}")
                conn.execute(text(f"DROP DATABASE IF EXISTS \"{test_db_name}\" WITH (FORCE)"))
                print("✅ [成功] 清理完成。")
            sync_maint_engine.dispose()
        print("="*80)
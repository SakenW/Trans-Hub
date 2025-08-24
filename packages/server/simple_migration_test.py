#!/usr/bin/env python3
"""
简单的迁移测试脚本
用于验证Alembic迁移是否正确创建表
"""

import os
import tempfile
from pathlib import Path

# 添加src目录到Python路径
import sys
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from trans_hub.bootstrap.init import create_app_config
from sqlalchemy import create_engine, text
import subprocess

def main():
    print("=" * 60)
    print("简单迁移测试")
    print("=" * 60)
    
    # 创建临时SQLite文件
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        temp_db_path = tmp_file.name
    
    try:
        print(f"\n1. 创建临时数据库: {temp_db_path}")
        
        # 设置环境变量
        temp_db_url = f"sqlite+aiosqlite:///{temp_db_path}"
        os.environ["TRANSHUB_DATABASE_URL"] = temp_db_url
        print(f"   设置数据库URL: {temp_db_url}")
        
        # 创建同步引擎来检查表
        sync_db_url = f"sqlite:///{temp_db_path}"
        engine = create_engine(sync_db_url)
        
        print("\n2. 迁移前检查表")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = [row[0] for row in result]
            print(f"   找到 {len(tables)} 个表: {tables}")
        
        print("\n3. 执行Alembic迁移")
        # 运行alembic upgrade head
        result = subprocess.run(
            ["poetry", "run", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent
        )
        
        print(f"   迁移退出码: {result.returncode}")
        if result.stdout:
            print(f"   标准输出:\n{result.stdout}")
        if result.stderr:
            print(f"   错误输出:\n{result.stderr}")
        
        print("\n4. 迁移后检查表")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = [row[0] for row in result]
            print(f"   找到 {len(tables)} 个表: {tables}")
            
            # 检查alembic_version表
            if "alembic_version" in tables:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                versions = [row[0] for row in result]
                print(f"   Alembic版本: {versions}")
        
        print("\n5. 检查业务表是否存在")
        expected_tables = ["projects", "content", "trans_rev", "trans_head"]
        missing_tables = []
        for table in expected_tables:
            if table not in tables:
                missing_tables.append(table)
        
        if missing_tables:
            print(f"   ❌ 缺失的业务表: {missing_tables}")
        else:
            print(f"   ✅ 所有业务表都已创建")
            
    finally:
        # 清理临时文件
        if os.path.exists(temp_db_path):
            os.unlink(temp_db_path)
            print(f"\n6. 清理临时文件: {temp_db_path}")

if __name__ == "__main__":
    main()
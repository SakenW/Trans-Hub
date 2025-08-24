#!/usr/bin/env python3
# test_fixture_debug.py

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

@pytest.mark.asyncio
async def test_migrated_db_fixture(migrated_db: AsyncEngine):
    """测试migrated_db fixture是否正确创建了表"""
    async with migrated_db.begin() as conn:
        # 检查schema是否存在
        result = await conn.execute(text("""
            SELECT schema_name FROM information_schema.schemata
            WHERE schema_name = 'th'
        """))
        schemas = result.fetchall()
        print(f"th schema存在: {len(schemas) > 0}")

        # 检查表是否存在
        result = await conn.execute(text("""
            SELECT schemaname, tablename
            FROM pg_tables
            WHERE schemaname = 'th'
            ORDER BY tablename
        """))
        tables = result.fetchall()
        print(f"th schema中的表: {[t[1] for t in tables]}")

        # 检查alembic_version表
        try:
            result = await conn.execute(text("""
                SELECT version_num FROM th.alembic_version
            """))
            version = result.scalar()
            print(f"当前迁移版本: {version}")
        except Exception as e:
            print(f"查询alembic_version失败: {e}")

        # 检查projects表是否存在
        try:
            result = await conn.execute(text("""
                SELECT COUNT(*) FROM th.projects
            """))
            count = result.scalar()
            print(f"projects表存在，行数: {count}")
        except Exception as e:
            print(f"查询projects表失败: {e}")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

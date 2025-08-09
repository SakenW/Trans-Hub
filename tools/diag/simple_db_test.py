# tools/diag/simple_db_test.py
"""
一个简化的脚本，用于测试数据库连接。
"""

import asyncio
import asyncpg


async def test_connection() -> None:
    """测试数据库连接。"""
    # 使用硬编码的数据库 URL 进行测试
    database_url = "postgresql://transhub_db:D4nBsHYGiGSSQpJc@192.168.50.111:5432/transhub_db"
    print(f"尝试连接到数据库: {database_url}")
    
    try:
        # 尝试连接数据库，设置连接超时
        conn = await asyncpg.connect(database_url, timeout=10.0)
        print("✅ 成功建立数据库连接")
        
        # 执行一个简单的查询
        result = await conn.fetchval("SELECT 1")
        print(f"✅ 成功执行查询，结果: {result}")
        
        # 关闭连接
        await conn.close()
        print("✅ 成功关闭数据库连接")
        
    except asyncio.TimeoutError:
        print("❌ 数据库连接超时")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        import traceback
        traceback.print_exc()


async def main() -> None:
    """主函数。"""
    print("--- 简化数据库连接测试开始 ---")
    await test_connection()
    print("--- 测试结束 ---")


if __name__ == "__main__":
    asyncio.run(main())
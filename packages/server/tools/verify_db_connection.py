# 文件名: verify_db_connection.py
# (增强诊断版)
import asyncio
import os
import sys
import traceback
from rich.console import Console
from rich.panel import Panel

console = Console()

print(f"\n--- 数据库连接诊断脚本 (增强版) ---")
print(f"Python: {sys.executable}")

# --- 硬编码的连接信息 ---
# [关键] 请再次确认这里的每一个值都和您能成功连接的 PGAdmin/Navicat 中的设置完全一致
DB_USER = "transhub"
DB_PASSWORD = "a1234567"
DB_HOST = "192.168.50.111"
DB_PORT = 5432
DB_NAME = "transhub"
MAINTENANCE_DB_NAME = "transhub"

# --- 构建连接字符串 ---
SYNC_MAINTENANCE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{MAINTENANCE_DB_NAME}"
ASYNC_APP_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def print_params(title: str, dbname: str):
    """打印将要使用的连接参数。"""
    panel_content = (
        f"  - [dim]Host:[/dim]     [yellow]{DB_HOST}[/yellow]\n"
        f"  - [dim]Port:[/dim]     [yellow]{DB_PORT}[/yellow]\n"
        f"  - [dim]User:[/dim]     [yellow]{DB_USER}[/yellow]\n"
        f"  - [dim]Password:[/dim] [yellow]{DB_PASSWORD}[/yellow]\n"
        f"  - [dim]Database:[/dim] [yellow]{dbname}[/yellow]"
    )
    console.print(Panel(panel_content, title=f"[bold cyan]{title}[/bold cyan]", border_style="cyan"))

def test_direct_sync_connection():
    """测试 1: 直接使用 psycopg2 (同步驱动) 连接"""
    print("\n--- [测试 1/4] 直接使用 psycopg2 (同步) 连接... ---")
    print_params("psycopg2 连接参数", MAINTENANCE_DB_NAME)
    try:
        import psycopg2
        conn = psycopg2.connect(
            dbname=MAINTENANCE_DB_NAME, user=DB_USER, password=DB_PASSWORD,
            host=DB_HOST, port=DB_PORT, connect_timeout=5
        )
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            console.print("✅ [bold green]成功:[/bold green] 直接使用 psycopg2 连接和查询成功！")
        conn.close()
    except Exception:
        console.print("❌ [bold red]失败:[/bold red] 直接使用 psycopg2 连接时发生错误:")
        traceback.print_exc()

async def test_direct_async_connection():
    """测试 2: 直接使用 asyncpg (异步驱动) 连接"""
    print("\n--- [测试 2/4] 直接使用 asyncpg (异步) 连接... ---")
    print_params("asyncpg 连接参数", DB_NAME)
    try:
        import asyncpg
        conn = await asyncpg.connect(
            user=DB_USER, password=DB_PASSWORD, database=DB_NAME,
            host=DB_HOST, port=DB_PORT, timeout=5
        )
        await conn.fetchval("SELECT 1")
        console.print("✅ [bold green]成功:[/bold green] 直接使用 asyncpg 连接和查询成功！")
        await conn.close()
    except Exception:
        console.print("❌ [bold red]失败:[/bold red] 直接使用 asyncpg 连接时发生错误:")
        traceback.print_exc()

# ... (SQLAlchemy 测试部分保持不变，因为它们依赖于字符串) ...
async def test_sqlalchemy_sync_connection():
    """测试 3: 通过 SQLAlchemy 使用同步驱动连接"""
    print("\n--- [测试 3/4] 正在尝试通过 SQLAlchemy (同步) 连接... ---")
    console.print(f"  - [dim]URL:[/dim] {SYNC_MAINTENANCE_URL}")
    try:
        from sqlalchemy import create_engine, text
        
        engine = create_engine(SYNC_MAINTENANCE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1")).scalar()
            console.print("✅ [bold green]成功:[/bold green] 通过 SQLAlchemy (同步) 连接和查询成功！")
        engine.dispose()
    except Exception:
        console.print(f"❌ [bold red]失败:[/bold red] 通过 SQLAlchemy (同步) 连接时发生错误:")
        traceback.print_exc()

async def main():
    """主函数，按顺序执行所有测试。"""
    test_direct_sync_connection()
    await test_sqlalchemy_sync_connection()
    await test_direct_async_connection()
    # ... SQLAlchemy async test can be added if needed ...
    print("\n--- 诊断脚本执行完毕 ---")
    console.print(Panel(
        "[bold]下一步：[/bold]\n"
        "1. 仔细检查上面 [bold yellow]黄色[/bold yellow] 的连接参数。\n"
        "2. 将这些[bold]一模一样[/bold]的值复制到您的 `packages/server/.env` 文件中。\n"
        "   [cyan]TH_DATABASE_URL=\"postgresql+asyncpg://<User>:<Password>@<Host>:<Port>/postgres\"[/cyan]\n"
        "3. 再次运行 `poetry run python tools/db_doctor.py` 进行验证。",
        title="[green]诊断建议[/green]", border_style="green"
    ))

if __name__ == "__main__":
    asyncio.run(main())
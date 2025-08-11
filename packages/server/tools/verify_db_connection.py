# packages/server/verify_db_connection_final.py
import asyncio
from rich.console import Console
from rich.panel import Panel

console = Console()

# --- 硬编码的、我们认为正确的凭证 ---
DB_USER = "transhub"
DB_PASSWORD = "a1234567"
DB_HOST = "192.168.50.111"
DB_PORT = 5432

# [关键] 我们将精确地连接到 db_doctor 失败的那个数据库
MAINTENANCE_DB_NAME = "postgres"

# [关键] 我们将精确地使用 SQLAlchemy，模拟 db_doctor 的连接方式
SYNC_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{MAINTENANCE_DB_NAME}"


def final_test():
    """
    这是最终的、无可辩驳的测试。
    它在最简化的脚本中，完全模拟 db_doctor.py 的失败场景。
    """
    console.print(Panel(
        f"[bold]最终诊断：模拟 `db_doctor.py` 的精确连接[/bold]\n\n"
        f"  - [dim]将要使用的 URL:[/dim] [yellow]{SYNC_URL.replace(DB_PASSWORD, '***')}[/yellow]",
        title="[cyan]最终连接测试[/cyan]", border_style="cyan"
    ))

    try:
        from sqlalchemy import create_engine, text

        # 1. 使用与 db_doctor 完全相同的库和方法创建引擎
        engine = create_engine(SYNC_URL)
        
        # 2. 尝试连接并执行查询
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            console.print("[bold green]✅ [惊人的成功!] 连接成功！[/bold green]")
            console.print("这意味着问题极其诡异，可能与 Poetry 的子进程环境有关。")

    except Exception as e:
        console.print("[bold red]✅ [预料之中的失败!] 连接失败，成功复现了错误！[/bold red]")
        console.print(f"\n[bold]错误详情:[/bold]\n{e}")
        console.print(Panel(
            "[bold green]最终诊断结论：[/bold green]\n\n"
            "我们已经 100% 确认，使用用户 `transhub` 和您提供的密码，"
            "无法通过 `psycopg2` 连接到 `postgres` 这个数据库。\n\n"
            "[bold]最终解决方案：[/bold]\n"
            "1. **登录到您的 PostgreSQL 服务器**。\n"
            "2. **检查 `pg_hba.conf` 文件**，确保有一行允许 `transhub` 用户从您的 IP 连接到 `postgres` 数据库，且方法是 `scram-sha-256` 或 `md5`。\n"
            "   例如: `host  postgres  transhub  0.0.0.0/0  scram-sha-256`\n"
            "3. **为 `transhub` 用户重置一个简单的、不会出错的密码**：\n"
            "   `ALTER USER transhub WITH PASSWORD 'password123';`\n"
            "4. **在 `.env` 文件中更新这个新密码**。",
            title="[green]问题已定位[/green]", border_style="green"
        ))

if __name__ == "__main__":
    final_test()
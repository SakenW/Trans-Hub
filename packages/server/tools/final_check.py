# packages/server/final_check.py
import os
import sys
import psycopg2
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# --- 硬编码的、已知可行的凭证 ---
DB_PARAMS = {
    "host": "192.168.50.111",
    "port": 5432,
    "user": "transhub",
    "password": "a1234567",
    "dbname": "postgres",
    "connect_timeout": 3,
}

# --- 模拟应用构造的 DSN 字符串 ---
DSN_STRING = (
    f"postgresql://{DB_PARAMS['user']}:{DB_PARAMS['password']}"
    f"@{DB_PARAMS['host']}:{DB_PARAMS['port']}/{DB_PARAMS['dbname']}"
)

def check_env_variables():
    """检查并打印所有相关的 PG* 环境变量。"""
    table = Table(title="[bold cyan]相关的 PostgreSQL 环境变量[/bold cyan]")
    table.add_column("变量名", style="cyan")
    table.add_column("值")

    found_any = False
    for var in ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"]:
        value = os.getenv(var)
        if value:
            table.add_row(var, f"[bold yellow]{value}[/bold yellow]")
            found_any = True
        else:
            table.add_row(var, "[dim]未设置[/dim]")
    
    if not found_any:
        console.print("[green]✅ 检查完毕：没有发现任何可能冲突的 PG* 环境变量。[/green]")
    else:
        console.print("[bold red]⚠️ 警告：检测到以下 PG* 环境变量，它们可能会覆盖连接参数！[/bold red]")
    
    console.print(table)


def test_direct_params_connection():
    """方法一：直接通过关键字参数连接 (模拟 verify_db_connection.py)。"""
    console.print("\n" + "="*50)
    console.print("[bold]测试 1：直接使用参数连接 (最高优先级)[/bold]")
    try:
        psycopg2.connect(**DB_PARAMS)
        console.print("[bold green]✅ [成功] 使用直接参数连接成功！[/bold green]")
    except Exception as e:
        console.print(f"❌ [失败] 使用直接参数连接失败: {e}")


def test_dsn_string_connection():
    """方法二：通过 DSN 字符串连接 (模拟 db_doctor.py / SQLAlchemy)。"""
    console.print("\n" + "="*50)
    console.print("[bold]测试 2：使用 DSN 字符串连接 (可能被环境变量覆盖)[/bold]")
    try:
        # 隐藏密码再打印
        printable_dsn = DSN_STRING.replace(DB_PARAMS["password"], "***")
        console.print(f"  - 尝试使用的 DSN: {printable_dsn}")
        psycopg2.connect(DSN_STRING)
        console.print("[bold green]✅ [成功] 使用 DSN 字符串连接成功！[/bold green]")
    except Exception as e:
        console.print(f"❌ [失败] 使用 DSN 字符串连接失败: {e}")
        console.print("[bold red]👉 这个失败确认了问题在于 DSN 解析或环境变量覆盖。[/bold red]")


if __name__ == "__main__":
    check_env_variables()
    test_direct_params_connection()
    test_dsn_string_connection()
    console.print("\n" + "="*50)
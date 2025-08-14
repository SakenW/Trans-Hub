# packages/server/final_env_check.py
import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def check_postgres_env_variables():
    """
    检查并打印所有可能影响 psycopg2 和 libpq 连接的环境变量。
    """
    console.print(
        Panel(
            "[bold cyan]PostgreSQL 环境变量最终诊断[/bold cyan]",
            subtitle="检查是否存在覆盖连接字符串的环境变量",
            border_style="red",
        )
    )

    table = Table(title="环境变量检查结果")
    table.add_column("环境变量", style="cyan", width=20)
    table.add_column("值", style="yellow")
    table.add_column("说明", style="dim")

    found_conflict = False

    # 优先级最高的 libpq 环境变量
    pg_vars = [
        "PGHOST",
        "PGHOSTADDR",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGPASSFILE",
    ]

    for var in pg_vars:
        value = os.getenv(var)
        if value:
            table.add_row(
                var,
                value,
                "[bold red]发现！这个变量可能会覆盖您的 DSN 设置！[/bold red]",
            )
            found_conflict = True
        else:
            table.add_row(var, "[green]未设置[/green]", "安全")

    console.print(table)

    if found_conflict:
        console.print(
            Panel(
                "[bold red]诊断结论：[/bold red]\n\n"
                "检测到一个或多个 PostgreSQL 环境变量 (PG*).\n"
                "这些变量的优先级高于连接字符串 (DSN) 中的设置，"
                "这很可能是导致“密码认证失败”的根本原因。\n\n"
                "[bold]解决方案：[/bold]\n"
                "1. 打开您的 Shell 配置文件 (例如 `~/.zshrc`, `~/.bash_profile`)。\n"
                "2. 找到并 **删除或注释掉** (`#`) 所有 `export PG...` 相关的行。\n"
                "3. **完全关闭并重新打开**您的终端，以使更改生效。\n"
                "4. 再次运行 `db_doctor.py`。",
                title="[bold red]发现潜在的环境变量冲突！[/bold red]",
                border_style="red",
            )
        )
    else:
        console.print(
            Panel(
                "[bold green]诊断结论：[/bold green]\n\n"
                "未检测到任何冲突的 PostgreSQL 环境变量。\n"
                "如果连接仍然失败，问题可能与本地 `.pgpass` 文件或网络策略有关，但这非常罕见。",
                title="[bold green]未发现明显的环境变量冲突[/bold green]",
                border_style="green",
            )
        )


if __name__ == "__main__":
    check_postgres_env_variables()

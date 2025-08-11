# packages/server/tools/db_doctor_ultimate.py
"""
终极诊断工具。
不依赖任何项目配置，使用硬编码凭证和最小化导入。
"""
import sys
from pathlib import Path
import questionary
from sqlalchemy import create_engine, text, URL
from rich.console import Console

console = Console()

# --- 100% 确定的、已知可行的硬编码凭证 ---
DB_PARAMS = {
    "username": "transhub",
    "password": "a1234567",
    "host": "192.168.50.111",
    "port": 5432
}
MAINTENANCE_DB = "postgres"

def run_ultimate_test():
    """执行终极连接测试。"""
    console.print("\n--- [终极诊断] 正在以最小化依赖的方式连接... ---")
    
    try:
        # 使用关键字参数构造 URL，这是最不可能出错的方式
        maintenance_url = URL.create(
            "postgresql+psycopg2",
            database=MAINTENANCE_DB,
            **DB_PARAMS
        )
        engine = create_engine(maintenance_url)

        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            console.print(f"[bold green]✅✅✅ [终极成功!] 连接成功！查询结果: {result}[/bold green]")
            console.print("\n[bold]结论：[/bold] 您的环境现在是干净的。请立即运行 `pytest`。")

    except Exception as e:
        console.print("[bold red]❌❌❌ [终极失败!] 即使在最纯净的环境下连接依然失败。[/bold red]")
        console.print(f"\n[bold]错误详情:[/bold]\n{e}")
        console.print("\n[bold]最终建议：[/bold] 问题已超出 Python 和 Poetry 的范畴，强烈建议在一个干净的 Docker 容器中重建开发环境，以排除所有系统级干扰。")

if __name__ == "__main__":
    run_ultimate_test()
# packages/server/final_conclusive_test.py
"""
最终诊断脚本。
它只做一件事：加载 .env 配置，并尝试连接到维护数据库。
"""
import os
import sys
from pathlib import Path

# --- 路径设置 ---
try:
    src_path = Path(__file__).resolve().parent / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
except (ImportError, IndexError):
    print("错误: 无法设置 Python 路径。")
    sys.exit(1)

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from rich.console import Console

console = Console()

def run_final_test():
    """执行最终的连接测试。"""
    console.print("\n--- [最终诊断脚本] 启动 ---")
    
    # 1. 强制加载 .env 文件
    env_path = Path.cwd() / ".env"
    if not env_path.is_file():
        console.print(f"❌ [失败] 在当前目录找不到 .env 文件: {env_path}")
        return
    
    load_dotenv(dotenv_path=env_path, override=True)
    console.print(f"✅ [成功] 已加载 .env 文件: {env_path}")

    # 2. 从环境变量中获取 URL
    db_url_str = os.getenv("TH_MAINTENANCE_DATABASE_URL")
    if not db_url_str:
        console.print("❌ [失败] 在 .env 文件或环境变量中找不到 TH_MAINTENANCE_DATABASE_URL。")
        return
    
    console.print(f"  - 读取到的维护库 URL: [yellow]{db_url_str}[/yellow]")
    
    # 3. 构建同步 URL
    try:
        sync_url = str(make_url(db_url_str).set(drivername="postgresql+psycopg2"))
        console.print(f"  - 将用于连接的同步 URL: [cyan]{sync_url.replace(make_url(db_url_str).password or '***', '***')}[/cyan]")
    except Exception as e:
        console.print(f"❌ [失败] 解析 URL 时出错: {e}")
        return

    # 4. 尝试连接
    console.print("\n--- 正在尝试连接... ---")
    try:
        engine = create_engine(sync_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            console.print(f"[bold green]✅✅✅ [终极成功!] 连接成功！查询结果: {result}[/bold green]")
            console.print("\n[bold]结论：[/bold] 您的环境和凭证是正确的。问题可能出在 `db_doctor.py` 与 `questionary` 库的复杂交互中。")
            console.print("您现在可以安全地继续运行 `poetry run pytest -v`。")

    except Exception as e:
        console.print("[bold red]❌❌❌ [终极失败!] 连接失败，成功复现了静默崩溃！[/bold red]")
        console.print(f"\n[bold]错误详情:[/bold]\n{e}")
        console.print("\n[bold]结论：[/bold] 这是一个非常深层次的环境问题，可能与 `libpq` 库的版本或 SSL 配置有关。")
        console.print("建议的下一步是在一个全新的、干净的操作系统或 Docker 容器中重试。")


if __name__ == "__main__":
    run_final_test()
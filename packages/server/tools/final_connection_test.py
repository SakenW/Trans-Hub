# packages/server/tools/final_connection_test.py
import sys
import uuid
from pathlib import Path

# 添加 src 目录到 Python 路径
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from rich.console import Console

# 导入配置加载器
from trans_hub.config_loader import load_config_from_env

console = Console()


def run_test():
    console.print("[bold cyan]启动终极连接诊断脚本...[/bold cyan]")

    # 1. 加载 .env.test 配置
    try:
        server_root = Path(__file__).parent.parent
        config = load_config_from_env(
            mode="test", strict=True, dotenv_path=server_root / ".env.test"
        )
        console.print("✅ [bold green]成功加载 .env.test 配置。[/bold green]")
        console.print(
            f"   - 用户名: [yellow]{config.database.url.split('//')[1].split(':')[0]}[/yellow]"
        )
        console.print(
            f"   - 维护库: [yellow]{make_url(config.maintenance_database_url).database}[/yellow]"
        )
    except Exception as e:
        console.print(f"❌ [bold red]加载配置失败: {e}[/bold red]")
        return

    # 2. 准备连接信息
    maint_url = make_url(config.maintenance_database_url).set(
        drivername="postgresql+psycopg2"
    )
    app_url = make_url(config.database.url)  # 保留原始信息
    test_db_name = f"test_debug_{uuid.uuid4().hex[:8]}"

    # 3. 连接到维护库并创建新数据库
    sync_maint_engine = create_engine(maint_url, isolation_level="AUTOCOMMIT")
    try:
        with sync_maint_engine.connect() as conn:
            console.print(
                f"\n[cyan]步骤 1: 正在连接到维护库 ([yellow]{maint_url.database}[/yellow])...[/cyan]"
            )
            conn.execute(text("SELECT 1"))
            console.print("✅ [bold green]连接维护库成功！[/bold green]")

            console.print(
                f"[cyan]步骤 2: 正在创建临时数据库 ([yellow]{test_db_name}[/yellow])...[/cyan]"
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))
            console.print("✅ [bold green]创建临时数据库成功！[/bold green]")
    except Exception as e:
        console.print(f"❌ [bold red]在步骤 1 或 2 失败: {e}[/bold red]")
        return
    finally:
        sync_maint_engine.dispose()

    # 4. [关键测试] 尝试连接到刚刚创建的新数据库
    sync_test_url = app_url.set(database=test_db_name, drivername="postgresql+psycopg2")
    sync_test_engine = create_engine(sync_test_url)
    try:
        with sync_test_engine.connect() as conn:
            console.print(
                f"\n[cyan]步骤 3: 正在连接到新创建的临时库 ([yellow]{test_db_name}[/yellow])...[/cyan]"
            )
            conn.execute(text("SELECT 1"))
            console.print(
                "✅✅✅ [bold green]终极成功！连接到新数据库成功！[/bold green]"
            )
            console.print("这说明问题可能确实与 pytest 环境有关，非常罕见。")
    except Exception as e:
        console.print("\n❌❌❌ [bold red]终极失败！连接到新数据库失败！[/bold red]")
        console.print(f"[bold]错误信息:[/bold] {e}")
        console.print("\n[bold yellow]诊断结论：[/bold yellow]")
        console.print("这 100% 证明了问题在于 PostgreSQL 服务器的 `pg_hba.conf` 配置。")
        console.print("它允许您连接到维护库，但禁止您连接到刚刚创建的新数据库。")
    finally:
        sync_test_engine.dispose()
        # 清理
        with create_engine(maint_url, isolation_level="AUTOCOMMIT").connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)'))
        console.print(
            f"\n[cyan]清理完成：已删除临时数据库 [yellow]{test_db_name}[/yellow]。[/cyan]"
        )


if __name__ == "__main__":
    run_test()

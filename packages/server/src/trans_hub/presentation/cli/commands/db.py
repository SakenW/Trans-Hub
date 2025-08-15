# packages/server/src/trans_hub/presentation/cli/commands/db.py
"""
处理数据库迁移相关的 CLI 命令。

口径：
- 仅使用 TRANSHUB_* 环境变量（嵌套用双下划线 "__"），不做历史兼容。
- Alembic 迁移必须使用“同步驱动”，但仍连接到“目标业务库”本身：
  * PostgreSQL  -> postgresql+psycopg://.../<业务库>
  * SQLite      -> sqlite://...
  * MySQL       -> mysql+pymysql://.../<业务库>
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from sqlalchemy.engine.url import make_url

from trans_hub.config_loader import load_config_from_env

app = typer.Typer(help="数据库管理命令 (迁移等)。")
console = Console()


def _find_alembic_ini(start: Optional[Path] = None) -> Path:
    """
    自下而上查找 packages/server/alembic.ini，兼容从不同工作目录调用。
    优先顺序：
      1) <任意上层>/packages/server/alembic.ini
      2) CWD/packages/server/alembic.ini
      3) <任意上层>/alembic.ini （兜底）
    """
    start = (start or Path(__file__).resolve()).parent
    # 1) 向上查找 packages/server/alembic.ini
    for p in [*start.parents, start]:
        cand = p / "packages" / "server" / "alembic.ini"
        if cand.is_file():
            return cand

    # 2) CWD
    cand = Path.cwd() / "packages" / "server" / "alembic.ini"
    if cand.is_file():
        return cand

    # 3) 兜底：向上查找裸的 alembic.ini
    for p in [*start.parents, start, *Path.cwd().parents, Path.cwd()]:
        cand = p / "alembic.ini"
        if cand.is_file():
            return cand

    raise FileNotFoundError("未找到 Alembic 配置文件 'alembic.ini'。")


def _to_sync_driver(async_dsn: str) -> str:
    """
    将运行期异步 DSN 转为同步 DSN（仅切 driver，保留主机/库名等）。
    """
    url = make_url(async_dsn)
    backend = url.get_backend_name()  # 'postgresql' | 'sqlite' | 'mysql' | ...
    if backend == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    elif backend == "sqlite":
        # 同步 sqlite 驱动名就是 'sqlite'
        url = url.set(drivername="sqlite")
    elif backend == "mysql":
        url = url.set(drivername="mysql+pymysql")
    else:
        raise typer.BadParameter(
            f"不支持的数据库后端：{backend!r}（仅支持 postgresql/sqlite/mysql）"
        )
    return str(url)


@app.command("migrate")
def db_migrate() -> None:
    """
    运行数据库迁移：使用 Alembic 将数据库 Schema 升级到最新版本。
    - 读取 TRANSHUB_* 配置；
    - 将异步 DSN 转为同步 DSN；
    - 执行 upgrade head。
    """
    console.print("[cyan]正在启动数据库迁移流程...[/cyan]")
    try:
        from alembic import command
        from alembic.config import Config as AlembicConfig

        # 仅认 TRANSHUB_*，严格模式；test 模式会在 .env 基础上加载 .env.test 覆盖
        cfg = load_config_from_env(mode="test", strict=True)

        # 目标业务库（仍是你的主库），但 driver 替换为同步驱动
        sync_db_url = _to_sync_driver(cfg.database.url)

        alembic_cfg_path = _find_alembic_ini()
        console.print(f"使用 Alembic 配置文件: [dim]{alembic_cfg_path}[/dim]")

        alembic_cfg = AlembicConfig(str(alembic_cfg_path))
        alembic_cfg.set_main_option("sqlalchemy.url", sync_db_url)

        console.print(f"迁移目标数据库: [yellow]{sync_db_url}[/yellow]")
        command.upgrade(alembic_cfg, "head")

        console.print("[bold green]✅ 数据库迁移成功完成！[/bold green]")
    except Exception as e:
        console.print(f"[bold red]❌ 数据库迁移失败: {e}[/bold red]")
        console.print_exception(show_locals=True)
        raise typer.Exit(code=1)


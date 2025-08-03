# trans_hub/cli/__init__.py
"""
Trans-Hub CLI 模块入口。
"""

import asyncio
import functools
from typing import Any, Callable, Optional

import structlog
import typer
from rich.console import Console

from trans_hub.cli.gc.main import gc as gc_command
from trans_hub.cli.request.main import request as request_command
from trans_hub.cli.worker.main import run_worker
from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator

from trans_hub.utils import validate_lang_codes

from trans_hub.logging_config import setup_logging


log = structlog.get_logger("trans_hub.cli")
console = Console()
DEFAULT_BATCH_SIZE = TransHubConfig().batch_size

# 创建Typer应用实例
app = typer.Typer(help="Trans-Hub 命令行工具")

# 全局状态管理
# 注意：这里简化了状态管理，实际项目中可能需要更复杂的机制
_coordinator: Optional[Coordinator] = None
_loop: Optional[asyncio.AbstractEventLoop] = None


def _initialize_coordinator(
    skip_init: bool = False,
) -> tuple[Coordinator, asyncio.AbstractEventLoop]:
    """
    初始化协调器和事件循环。
    """


class State:
    """
    全局状态类，用于存储CLI运行时的状态信息。
    """

    def __init__(self) -> None:
        self.coordinator: Optional[Coordinator] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None


def _initialize_coordinator() -> tuple[Coordinator, asyncio.AbstractEventLoop]:
    """初始化协调器和事件循环并执行初始化。"""

    global _coordinator, _loop

    if (
        _coordinator is not None
        and _loop is not None
        and _coordinator.initialized
    ):
        return _coordinator, _loop

    # 创建新的事件循环
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    # 初始化协调器
    config = TransHubConfig()
    setup_logging(
        log_level=config.logging.level,
        log_format=config.logging.format,
    )
    from trans_hub.persistence.sqlite import SQLitePersistenceHandler

    _persistence_handler = SQLitePersistenceHandler(config.database_url)
    _coordinator = Coordinator(config, _persistence_handler)
    _loop.run_until_complete(_coordinator.initialize())

    return _coordinator, _loop


def reset_state() -> None:
    """重置全局协调器和事件循环状态。"""
    global _coordinator, _loop
    _coordinator = None
    _loop = None


def _with_coordinator(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    装饰器，用于为CLI命令提供协调器和事件循环。
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        global _coordinator, _loop
        # 初始化协调器和事件循环
        coordinator, loop = _initialize_coordinator()
        has_error = False
        try:
            # 将coordinator和loop添加到kwargs中
            kwargs["coordinator"] = coordinator
            kwargs["loop"] = loop
            # 调用原始函数
            return func(*args, **kwargs)
        except Exception as e:
            has_error = True
            log.error("命令执行失败", error=str(e), exc_info=True)
            console.print(f"[red]❌ 命令执行失败: {e}[/red]")
            raise typer.Exit(1)
        finally:

            global _coordinator, _loop
            try:
                if coordinator and loop:
                    loop.run_until_complete(coordinator.close())
            finally:
                if loop:
                    loop.close()
            _coordinator = None
            _loop = None

            if has_error:
                if coordinator and loop:
                    try:
                        loop.run_until_complete(coordinator.close())
                    finally:
                        loop.close()
                _coordinator = None
                _loop = None


    return wrapper


from trans_hub.cli.app.main import app as app_app

# 添加子命令
app.add_typer(app_app, name="app", help="应用主入口")


@app.command()
@_with_coordinator
def worker(
    coordinator: Coordinator,
    loop: asyncio.AbstractEventLoop,
    langs: list[str] = typer.Option([], "--lang", "-l", help="要处理的语言列表"),
    batch_size: int = typer.Option(
        DEFAULT_BATCH_SIZE,
        "--batch-size",
        "-b",
        help=f"每批处理的任务数量（默认读取配置 batch_size={DEFAULT_BATCH_SIZE}）",
    ),
    poll_interval: int = typer.Option(
        5, "--poll-interval", "-p", help="轮询间隔（秒）"
    ),
) -> None:
    """
    启动Trans-Hub Worker进程，处理待翻译任务。
    """
    # 校验语言代码
    validate_lang_codes(langs)

    # 创建关闭事件
    shutdown_event = asyncio.Event()
    run_worker(coordinator, loop, shutdown_event, langs, batch_size, poll_interval)


@app.command()
@_with_coordinator
def request(
    coordinator: Coordinator,
    loop: asyncio.AbstractEventLoop,
    text: str = typer.Argument(..., help="要翻译的文本内容"),
    target_lang: list[str] = typer.Option(..., "--target", "-t", help="目标语言列表"),
    source_lang: Optional[str] = typer.Option(
        None, "--source", "-s", help="源语言（可选，自动检测）"
    ),
    business_id: Optional[str] = typer.Option(
        None, "--business-id", "-b", help="业务ID（可选）"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="强制重新翻译，即使已有结果"
    ),
) -> None:
    """
    提交一个新的翻译请求到队列中。
    """
    # 校验目标语言代码
    validate_lang_codes(target_lang)

    request_command(
        coordinator, loop, text, target_lang, source_lang, business_id, force
    )


@app.command()
@_with_coordinator
def gc(
    coordinator: Coordinator,
    loop: asyncio.AbstractEventLoop,
    retention_days: int = typer.Option(90, "--retention-days", "-r", help="保留天数"),
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="仅预览，不执行删除"),
) -> None:
    """
    执行数据库垃圾回收，清理过期的、无关联的旧数据。
    """
    gc_command(coordinator, loop, retention_days, dry_run)


@app.command("db-migrate")
def db_migrate_cmd(
    database_url: str = typer.Option("", "--database-url", "-u", help="数据库URL"),
) -> None:
    """
    执行数据库迁移。
    """
    try:
        from trans_hub.cli.db.main import db_migrate

        db_migrate(database_url=database_url or "")
    except Exception as e:
        log.error("命令执行失败", error=str(e), exc_info=True)
        console.print(f"[red]❌ 命令执行失败: {e}[/red]")
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="显示版本信息并退出"),
) -> None:
    """
    Trans-Hub 命令行工具主入口。
    """
    if version:
        console.print("Trans-Hub CLI Version 1.0.0")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        # 没有指定子命令时显示帮助信息
        console.print(ctx.get_help())
        raise typer.Exit(0)


if __name__ == "__main__":
    app()

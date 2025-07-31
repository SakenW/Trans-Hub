# trans_hub/cli.py
"""
Trans-Hub 的官方命令行接口 (CLI)。

本工具提供了与 Trans-Hub 核心功能交互的入口，
包括运行后台工作进程、提交翻译请求和管理数据库。
"""

# --- 最终修复：严格遵循 PEP8 导入顺序 ---
# 1. 标准库导入
import asyncio
import sys
from pathlib import Path
from typing import List, Optional

# 2. 第三方库导入
import questionary
import structlog
import typer
from rich.console import Console
from rich.table import Table

# 3. sys.path 修改 (必须在本项目库导入之前)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 4. 本项目库导入
from trans_hub import __version__  # noqa: E402
from trans_hub.config import TransHubConfig  # noqa: E402
from trans_hub.coordinator import Coordinator  # noqa: E402
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402
from trans_hub.types import TranslationStatus  # noqa: E402

# --- 初始化 ---
app = typer.Typer(
    name="trans-hub",
    help="一个可嵌入的、带持久化存储的智能本地化（i18n）后端引擎。",
    add_completion=False,
)
db_app = typer.Typer(help="数据库管理命令。")
app.add_typer(db_app, name="db")

console = Console()
log = structlog.get_logger("trans_hub.cli")

# 全局协调器实例
coordinator = None


class State:
    """用于在 Typer 上下文中传递共享对象的容器。"""

    coordinator: Coordinator


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", "-V", help="显示版本号并退出。", is_eager=True
    ),
) -> None:
    """
    主回调函数，在任何命令执行前运行。
    负责显示版本信息和帮助信息。
    """
    if version:
        console.print(f"Trans-Hub version: [bold green]{__version__}[/bold green]")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()

    # 初始化协调器
    log.info("初始化协调器...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        coord = loop.run_until_complete(initialize_coordinator())
    finally:
        loop.close()

    # 将协调器实例传递给子命令
    ctx.obj = State()
    ctx.obj.coordinator = coord


@app.command()
async def run_worker(
    ctx: typer.Context,
    lang: List[str] = typer.Option(
        ..., "--lang", "-l", help="要处理的目标语言代码，可多次指定。"
    ),
    batch_size: int = typer.Option(
        50, "--batch-size", "-b", help="每个批次处理的任务数量。"
    ),
    polling_interval: int = typer.Option(
        5, "--interval", "-i", help="当队列为空时，轮询的间隔时间（秒）。"
    ),
) -> None:
    """
    启动一个或多个后台工作进程，持续处理待翻译任务。
    """
    coordinator: Coordinator = ctx.obj.coordinator
    log.info(
        "启动 Worker...",
        target_languages=lang,
        batch_size=batch_size,
        polling_interval=polling_interval,
    )

    async def process_language(target_lang: str) -> None:
        """处理单一语言的循环。"""
        while True:
            try:
                processed_count = 0
                async for result in coordinator.process_pending_translations(
                    target_lang, batch_size
                ):
                    processed_count += 1
                    if result.status == TranslationStatus.TRANSLATED:
                        log.info(
                            "翻译成功",
                            lang=target_lang,
                            original=f"'{result.original_content[:20]}...'",
                        )
                    else:
                        log.warning(
                            "翻译失败",
                            lang=target_lang,
                            original=f"'{result.original_content[:20]}...'",
                            error=result.error,
                        )

                if processed_count == 0:
                    log.debug(
                        "队列为空，休眠...", lang=target_lang, interval=polling_interval
                    )
                    await asyncio.sleep(polling_interval)
            except asyncio.CancelledError:
                log.info("Worker 收到停止信号，正在退出...", lang=target_lang)
                break
            except Exception:
                log.error(
                    "Worker 循环中发生未知错误，将在5秒后重试...",
                    lang=target_lang,
                    exc_info=True,
                )
                await asyncio.sleep(5)

    worker_tasks = [process_language(target_lang) for target_lang in lang]
    try:
        await asyncio.gather(*worker_tasks)
    except KeyboardInterrupt:
        log.info("收到用户中断信号，正在优雅地关闭 Worker...")


async def _async_request(
    ctx: typer.Context,
    text: str,
    target_lang: List[str],
    source_lang: Optional[str],
    business_id: Optional[str],
    force: bool,
) -> None:
    """
    异步提交翻译请求的内部函数。
    """
    coordinator: Coordinator = ctx.obj.coordinator
    log.info("收到新的翻译请求...", text=text, targets=target_lang, force=force)
    await coordinator.request(
        text_content=text,
        target_langs=target_lang,
        source_lang=source_lang,
        business_id=business_id,
        force_retranslate=force,
    )
    console.print("[green]✅ 翻译请求已成功提交！[/green]")


@app.command()
def request(
    ctx: typer.Context,
    text: str = typer.Argument(..., help="要翻译的原文。"),
    target_lang: List[str] = typer.Option(
        ..., "--target", "-t", help="目标语言代码，可多次指定。"
    ),
    source_lang: Optional[str] = typer.Option(
        None, "--source", "-s", help="源语言代码。"
    ),
    business_id: Optional[str] = typer.Option(None, "--id", help="用于追踪的业务ID。"),
    force: bool = typer.Option(False, "--force", help="强制重新翻译，即使已有缓存。"),
) -> None:
    """
    提交一个新的翻译请求到队列中。
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                _async_request(ctx, text, target_lang, source_lang, business_id, force)
            )
            # 请求处理完成后立即退出
            log.info("翻译请求处理完成，正在退出应用...")
            # 手动关闭协调器
            if hasattr(ctx.obj, "coordinator") and ctx.obj.coordinator:
                log.info("手动关闭协调器...")
                loop.run_until_complete(
                    asyncio.wait_for(ctx.obj.coordinator.close(), timeout=5.0)
                )
                log.info("协调器已关闭")
            # 强制退出
            import sys

            sys.exit(0)
        finally:
            loop.close()
    except Exception as e:
        log.error("请求处理失败", error=str(e), exc_info=True)
        raise typer.Exit(code=1)


@app.command()
async def gc(
    ctx: typer.Context,
    retention_days: int = typer.Option(
        90, "--days", "-d", help="保留最近多少天内的活跃任务。"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="只显示将被删除的条目数量，不实际执行删除操作。"
    ),
) -> None:
    """
    执行数据库垃圾回收，清理过期的、无关联的旧数据。
    """
    coordinator: Coordinator = ctx.obj.coordinator
    mode = "Dry Run" if dry_run else "执行"
    console.print(
        f"[yellow]即将为超过 {retention_days} 天的非活跃任务执行垃圾回收 "
        f"({mode})...[/yellow]"
    )

    report = await coordinator.run_garbage_collection(retention_days, True)

    table = Table(title="垃圾回收预报告")
    table.add_column("项目", style="cyan")
    table.add_column("将被删除数量", style="magenta", justify="right")
    table.add_row("关联任务 (Jobs)", str(report.get("deleted_jobs", 0)))
    table.add_row("原文内容 (Content)", str(report.get("deleted_content", 0)))
    table.add_row("上下文 (Contexts)", str(report.get("deleted_contexts", 0)))

    console.print(table)

    if all(v == 0 for v in report.values()):
        console.print("[green]数据库很干净，无需进行垃圾回收。[/green]")
        raise typer.Exit()

    if not dry_run:
        proceed = await questionary.confirm(
            "这是一个破坏性操作，是否继续执行删除？", default=False, auto_enter=False
        ).ask_async()

        if not proceed:
            console.print("[red]操作已取消。[/red]")
            raise typer.Abort()

        console.print("[yellow]正在执行删除操作...[/yellow]")
        final_report = await coordinator.run_garbage_collection(retention_days, False)
        console.print("[green]✅ 垃圾回收执行完毕！[/green]")
        assert final_report == report, "最终报告与预报告不符，可能存在并发问题"


@db_app.command("migrate")
def db_migrate(
    db_url: Optional[str] = typer.Option(
        None, "--db-url", help="覆盖配置中的数据库 URL (例如 'sqlite:///./new.db')。"
    ),
) -> None:
    """
    对数据库应用所有必要的迁移脚本，使其达到最新 Schema 版本。
    """
    setup_logging(log_level="INFO", log_format="console")

    config = TransHubConfig()
    final_db_url = db_url or config.database_url

    if not final_db_url.startswith("sqlite"):
        console.print(
            f"[red]错误: 目前只支持 SQLite 数据库。提供了: {final_db_url}[/red]"
        )
        raise typer.Exit(1)

    db_path = final_db_url.replace("sqlite:///", "")

    console.print(f"[cyan]正在对数据库应用迁移: {db_path}[/cyan]")
    try:
        apply_migrations(db_path)
        console.print("[green]✅ 数据库迁移成功！[/green]")
    except Exception as e:
        log.error("数据库迁移失败！", error=str(e), exc_info=True)
        raise typer.Exit(1)


async def initialize_coordinator() -> Coordinator:
    """
    异步初始化协调器。
    """
    global coordinator
    if coordinator is not None:
        return coordinator

    setup_logging(log_level="DEBUG", log_format="console")

    config = TransHubConfig()
    log.info("创建持久化处理器...")
    handler = create_persistence_handler(config)
    log.info("创建协调器...")
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        # 异步初始化协调器
        log.info("开始初始化协调器...")
        await coordinator.initialize()
        log.info("协调器初始化完成")

        # 注册清理函数
        def cleanup() -> None:
            log.info("应用程序退出，正在关闭协调器...")
            try:
                if coordinator:
                    close_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(close_loop)
                    close_loop.run_until_complete(
                        asyncio.wait_for(coordinator.close(), timeout=5.0)
                    )
                    close_loop.close()
            except Exception as e:
                log.error("关闭协调器时发生错误", error=str(e))

        import atexit

        atexit.register(cleanup)

        return coordinator
    except Exception as e:
        log.error("协调器初始化失败", error=str(e), exc_info=True)
        raise


def run_app() -> None:
    """
    运行应用程序。
    """
    try:
        # 运行Typer应用
        log.info("启动应用...")
        typer.run(app)
    except KeyboardInterrupt:
        log.info("应用程序被用户中断")
        raise typer.Exit(code=0)
    except Exception as e:
        log.error("应用程序执行出错", error=str(e), exc_info=True)
    finally:
        # 确保协调器已关闭
        global coordinator
        if coordinator:
            log.info("应用程序退出，正在关闭协调器...")
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    asyncio.wait_for(coordinator.close(), timeout=5.0)
                )
                loop.close()
                log.info("协调器已关闭")
            except Exception as e:
                log.error("关闭协调器时发生错误", error=str(e))
        log.info("应用程序已退出")


if __name__ == "__main__":
    run_app()

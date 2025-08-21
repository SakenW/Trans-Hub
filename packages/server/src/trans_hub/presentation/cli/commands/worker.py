# packages/server/src/trans_hub/presentation/cli/commands/worker.py
import asyncio

import structlog
import typer
from dependency_injector.wiring import Provide, inject
from rich.console import Console
from trans_hub.containers import ApplicationContainer

console = Console()
logger = structlog.get_logger(__name__)

app = typer.Typer(help="运行后台 Worker 进程。", no_args_is_help=True)


@app.command("run")
@inject
def run_workers(
    ctx: typer.Context,
    all_in_one: bool = typer.Option(
        False, "--all", help="在一个进程中运行所有可用的 Worker (用于开发)。"
    ),
    translator: bool = typer.Option(
        False, "--translator", help="独立启动翻译任务 Worker。"
    ),
    relay: bool = typer.Option(False, "--relay", help="独立启动 Outbox 中继 Worker。"),
    container: ApplicationContainer = Provide[ApplicationContainer],
):
    """
    启动一个或多个 Worker 进程。
    可以独立启动每个 Worker，或者使用 --all 在开发环境中一并启动。
    """
    if not any([all_in_one, translator, relay]):
        console.print(
            "[bold red]错误: 必须至少指定一个 Worker 类型 (--all, --translator, 或 --relay)。[/bold red]"
        )
        raise typer.Exit(1)

    shutdown_event = asyncio.Event()

    # 获取 Worker 实例
    translation_worker = container.workers.translation_worker()
    outbox_relay_worker = container.workers.outbox_relay_worker()
    config = container.pydantic_config()

    async def _run_tasks():
        tasks = []
        worker_map = {
            "translator": (translator, translation_worker, True),
            "relay": (relay, outbox_relay_worker, bool(config.redis.url)),
        }
        if all_in_one:
            tasks.append(translation_worker.run_loop(shutdown_event))
            if config.redis.url:
                tasks.append(outbox_relay_worker.run_loop(shutdown_event))
            else:
                logger.warning(
                    "Redis 未配置，All-in-one 模式将跳过 Outbox Relay Worker。"
                )
        else:
            for name, (is_flagged, worker_instance, can_run) in worker_map.items():
                if is_flagged:
                    if can_run:
                        tasks.append(worker_instance.run_loop(shutdown_event))
                    else:
                        console.print(
                            f"[bold red]错误: 无法启动 {name} Worker，缺少必要配置 (如 Redis)。[/bold red]"
                        )
                        raise typer.Exit(1)

        if not tasks:
            console.print("[bold yellow]警告: 没有要启动的 Worker。[/bold yellow]")
            return

        await asyncio.gather(*tasks)

    try:
        console.print("[cyan]🚀 正在启动指定的 Worker(s)...[/cyan]")
        asyncio.run(_run_tasks())
    except KeyboardInterrupt:
        logger.warning("收到键盘中断信号，正在关闭...")
        shutdown_event.set()
    except Exception as e:
        logger.error("Worker 进程意外终止。", error=e, exc_info=True)
        # 确保资源被关闭
        container.shutdown_resources()
        raise typer.Exit(1)

    # 正常退出时，main.py 中的 call_on_close 会处理资源关闭
    console.print("[bold green]✅ 所有 Worker 已请求关闭。等待资源释放...[/bold green]")

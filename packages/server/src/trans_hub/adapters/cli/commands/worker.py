# packages/server/src/trans_hub/adapters/cli/commands/worker.py
"""CLI 命令，用于启动后台 Workers。"""

import asyncio

import structlog
import typer
from dependency_injector.wiring import Provide, inject
from rich.console import Console

from trans_hub.di.container import AppContainer
from trans_hub.workers import _outbox_relay_worker, _translation_worker

console = Console()
logger = structlog.get_logger(__name__)

app = typer.Typer(help="运行后台 Worker 进程。", no_args_is_help=True)


@inject
async def _run_all_workers(container: AppContainer = Provide[AppContainer]):
    """在一个进程中并发运行所有 Worker。"""
    shutdown_event = asyncio.Event()

    # 从容器中获取已实例化的依赖
    config = await container.config()
    uow_factory = container.uow_factory()
    stream_producer = await container.stream_producer() if config.redis.url else None

    try:
        async with asyncio.TaskGroup() as tg:
            # 启动翻译 Worker
            tg.create_task(
                _translation_worker.run_worker_loop(container, shutdown_event)
            )
            
            # 如果配置了 Redis，启动 Outbox 中继 Worker
            if stream_producer:
                tg.create_task(
                    _outbox_relay_worker.run_relay_loop(
                        config, uow_factory, stream_producer, shutdown_event
                    )
                )
    except* Exception as eg:
        # TaskGroup 会自动取消所有任务，我们只需要设置关闭事件
        shutdown_event.set()
        # 重新抛出异常组中的第一个异常
        raise eg.exceptions[0]
    finally:
        logger.info("正在关闭所有 Worker 的共享资源...")
        db_engine = await container.db_engine()
        await db_engine.dispose()
        if config.redis.url:
            from trans_hub.infrastructure.redis._client import close_redis_client

            await close_redis_client()
        logger.info("共享资源已关闭。")


@inject
async def _run_workers_logic(
    all_in_one: bool,
    translator: bool,
    relay: bool,
    container: AppContainer = Provide[AppContainer],
):
    """
    启动一个或多个 Worker 进程的内部逻辑。
    """
    if not any([all_in_one, translator, relay]):
        console.print(
            "[bold red]错误: 必须至少指定一个 Worker 类型 (--all, --translator, 或 --relay)。[/bold red]"
        )
        raise typer.Exit(1)

    shutdown_event = asyncio.Event()

    try:
        if all_in_one:
            console.print("[cyan]🚀 正在以 All-in-One 模式启动所有 Workers...[/cyan]")
            await _run_all_workers(container=container)
        else:
            # 独立运行模式
            config = await container.config()
            uow_factory = container.uow_factory()
            db_engine = await container.db_engine()

            tasks = []
            if translator:
                console.print("[cyan]🚀 正在启动翻译 Worker...[/cyan]")
                tasks.append(
                    _translation_worker.run_worker_loop(
                        container, shutdown_event
                    )
                )

            if relay:
                if not config.redis.url:
                    console.print(
                        "[bold red]错误: 启动 Outbox Relay Worker 需要配置 Redis。[/bold red]"
                    )
                    raise typer.Exit(1)

                stream_producer = await container.stream_producer()

                console.print("[cyan]🚀 正在启动 Outbox Relay Worker...[/cyan]")
                tasks.append(
                    _outbox_relay_worker.run_relay_loop(
                        config, uow_factory, stream_producer, shutdown_event
                    )
                )

            # 使用 TaskGroup 进行结构化并发
            async with asyncio.TaskGroup() as tg:
                for task_coro in tasks:
                    tg.create_task(task_coro)
            
            await db_engine.dispose()
            if config.redis.url:
                from trans_hub.infrastructure.redis._client import (
                    close_redis_client,
                )

                await close_redis_client()

    except KeyboardInterrupt:
        logger.warning("收到键盘中断信号，正在关闭...")
        shutdown_event.set()
    except Exception as e:
        logger.error("Worker 进程意外终止。", error=e, exc_info=True)
        raise typer.Exit(1)

    console.print("[bold green]✅ 所有 Worker 已安全关闭。[/bold green]")


@app.command("run")
async def run_workers_cli(
    all_in_one: bool = typer.Option(
        False, "--all", help="在一个进程中运行所有可用的 Worker (用于开发)。"
    ),
    translator: bool = typer.Option(
        False, "--translator", help="独立启动翻译任务 Worker。"
    ),
    relay: bool = typer.Option(False, "--relay", help="独立启动 Outbox 中继 Worker。"),
):
    """
    启动一个或多个 Worker 进程。
    可以独立启动每个 Worker，或者使用 --all 在开发环境中一并启动。
    """
    await _run_workers_logic(all_in_one=all_in_one, translator=translator, relay=relay)

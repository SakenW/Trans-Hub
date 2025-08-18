# packages/server/src/trans_hub/presentation/cli/commands/worker.py
"""CLI 命令，用于启动后台 Workers。"""

import asyncio

import structlog
import typer
from rich.console import Console

from trans_hub.bootstrap import create_uow_factory
from trans_hub.config import TransHubConfig
from trans_hub.workers import _outbox_relay_worker, _translation_worker
from trans_hub.presentation.cli._state import CLISharedState

console = Console()
logger = structlog.get_logger(__name__)

app = typer.Typer(help="运行后台 Worker 进程。", no_args_is_help=True)


async def _run_all_workers(config: TransHubConfig):
    """在一个进程中并发运行所有 Worker。"""
    shutdown_event = asyncio.Event()
    uow_factory, db_engine = create_uow_factory(config)

    stream_producer = None
    if config.redis.url:
        from trans_hub.infrastructure.redis._client import (
            get_redis_client,
            close_redis_client,
        )
        from trans_hub.infrastructure.redis.streams import RedisStreamProducer

        redis_client = await get_redis_client(config)
        stream_producer = RedisStreamProducer(redis_client)
    else:
        logger.warning("Redis 未配置，Outbox Relay Worker 将不会启动。")

    tasks = [
        _translation_worker.run_worker_loop(config, uow_factory, shutdown_event),
    ]
    if stream_producer:
        tasks.append(
            _outbox_relay_worker.run_relay_loop(
                config, uow_factory, stream_producer, shutdown_event
            )
        )

    try:
        await asyncio.gather(*tasks)
    finally:
        logger.info("正在关闭所有 Worker 的共享资源...")
        await db_engine.dispose()
        if config.redis.url:
            await close_redis_client()
        logger.info("共享资源已关闭。")


@app.command("run")
def run_workers(
    ctx: typer.Context,
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
    state: CLISharedState = ctx.obj
    config = state.config

    if not any([all_in_one, translator, relay]):
        console.print(
            "[bold red]错误: 必须至少指定一个 Worker 类型 (--all, --translator, 或 --relay)。[/bold red]"
        )
        raise typer.Exit(1)

    shutdown_event = asyncio.Event()

    try:
        if all_in_one:
            console.print("[cyan]🚀 正在以 All-in-One 模式启动所有 Workers...[/cyan]")
            asyncio.run(_run_all_workers(config))
        else:
            # 独立运行模式
            uow_factory, db_engine = create_uow_factory(config)

            async def run_single_worker():
                tasks = []
                if translator:
                    console.print("[cyan]🚀 正在启动翻译 Worker...[/cyan]")
                    tasks.append(
                        _translation_worker.run_worker_loop(
                            config, uow_factory, shutdown_event
                        )
                    )

                if relay:
                    if not config.redis.url:
                        console.print(
                            "[bold red]错误: 启动 Outbox Relay Worker 需要配置 Redis。[/bold red]"
                        )
                        raise typer.Exit(1)

                    from trans_hub.infrastructure.redis._client import get_redis_client
                    from trans_hub.infrastructure.redis.streams import (
                        RedisStreamProducer,
                    )

                    redis_client = await get_redis_client(config)
                    stream_producer = RedisStreamProducer(redis_client)

                    console.print("[cyan]🚀 正在启动 Outbox Relay Worker...[/cyan]")
                    tasks.append(
                        _outbox_relay_worker.run_relay_loop(
                            config, uow_factory, stream_producer, shutdown_event
                        )
                    )

                await asyncio.gather(*tasks)
                await db_engine.dispose()
                if config.redis.url:
                    from trans_hub.infrastructure.redis._client import (
                        close_redis_client,
                    )

                    await close_redis_client()

            asyncio.run(run_single_worker())

    except KeyboardInterrupt:
        logger.warning("收到键盘中断信号，正在关闭...")
        shutdown_event.set()
    except Exception as e:
        logger.error("Worker 进程意外终止。", error=e, exc_info=True)
        raise typer.Exit(1)

    console.print("[bold green]✅ 所有 Worker 已安全关闭。[/bold green]")

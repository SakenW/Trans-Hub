# trans_hub/cli/status.py
# [v2.4 Refactor] 更新 'status' 子命令以适配新的 UIDA 和 rev/head 模型。
# 'publish' 和 'reject' 现在操作的是 revision ID。
import asyncio
import json
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel

from trans_hub.cli.state import State
from trans_hub.cli.utils import create_coordinator
from trans_hub.coordinator import Coordinator

console = Console()
status_app = typer.Typer(help="查询和管理翻译记录的状态")


async def _get_status(coordinator: Coordinator, get_params: dict[str, Any]) -> None:
    """异步执行状态查询的核心逻辑。"""
    try:
        await coordinator.initialize()
        result = await coordinator.get_translation(**get_params)
        if result:
            console.print(
                Panel(
                    JSON(json.dumps(result, ensure_ascii=False, indent=2)),
                    title=f"[green]✅ 找到已发布的翻译 for [bold]{get_params['target_lang']}[/bold][/green]",
                    border_style="green",
                    expand=False,
                )
            )
        else:
            console.print(
                f"[yellow]⚠️ 未找到 [bold]{get_params['target_lang']}[/bold] 的已发布翻译（或其回退）。"
                "请使用 `tools/inspect_db.py` 查看草稿或待审阅状态。[/yellow]"
            )
    finally:
        await coordinator.close()


@status_app.command("get")
def get_status(
    ctx: typer.Context,
    project_id: Annotated[
        str, typer.Option("--project-id", help="项目/租户的唯一标识符。")
    ],
    namespace: Annotated[str, typer.Option("--namespace", help="内容的命名空间。")],
    keys_json: Annotated[
        str, typer.Option("--keys-json", help="定位内容的上下文键集 (JSON 字符串)。")
    ],
    target_lang: Annotated[
        str, typer.Option("--target-lang", "-t", help="目标语言代码。")
    ],
    variant_key: Annotated[
        str, typer.Option("--variant", "-v", help="语言内变体。")
    ] = "-",
) -> None:
    """根据 UIDA 查询一条已发布的翻译记录，会自动应用回退逻辑。"""
    try:
        keys = json.loads(keys_json)
    except json.JSONDecodeError as e:
        console.print(f"[bold red]❌ Keys JSON 格式错误: {e}[/bold red]")
        raise typer.Exit(code=1) from e

    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    get_params = {
        "project_id": project_id,
        "namespace": namespace,
        "keys": keys,
        "target_lang": target_lang,
        "variant_key": variant_key,
    }
    asyncio.run(_get_status(coordinator, get_params))


async def _publish(coordinator: Coordinator, revision_id: str) -> None:
    """异步执行发布的逻辑。"""
    try:
        await coordinator.initialize()
        success = await coordinator.publish_translation(revision_id)
        if success:
            console.print(
                f"[green]✅ 修订 ID [bold]{revision_id}[/bold] 已成功发布！[/green]"
            )
        else:
            console.print(
                "[red]❌ 发布失败。修订可能不存在，或状态不是 'reviewed'，或已有已发布版本。[/red]"
            )
    finally:
        await coordinator.close()


@status_app.command("publish")
def publish_translation(
    ctx: typer.Context,
    revision_id: Annotated[
        str, typer.Argument(help="要发布的 'reviewed' 状态的翻译修订 ID。")
    ],
) -> None:
    """将一条 'reviewed' 状态的翻译修订发布。"""
    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    asyncio.run(_publish(coordinator, revision_id))


async def _reject(coordinator: Coordinator, revision_id: str) -> None:
    """异步执行拒绝的逻辑。"""
    try:
        await coordinator.initialize()
        success = await coordinator.reject_translation(revision_id)
        if success:
            console.print(
                f"[yellow]✅ 修订 ID [bold]{revision_id}[/bold] 已被拒绝。[/yellow]"
            )
        else:
            console.print("[red]❌ 操作失败。记录可能不存在或非当前修订。[/red]")
    finally:
        await coordinator.close()


@status_app.command("reject")
def reject_translation(
    ctx: typer.Context,
    revision_id: Annotated[str, typer.Argument(help="要拒绝的翻译修订的唯一 ID。")],
) -> None:
    """将一条翻译修订的状态设置为 'rejected'。"""
    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    asyncio.run(_reject(coordinator, revision_id))

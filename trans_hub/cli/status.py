# trans_hub/cli/status.py
"""处理翻译状态查询与管理的 CLI 命令。"""

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


async def _get_status(
    coordinator: Coordinator,
    project_id: str,
    namespace: str,
    keys: dict[str, Any],
    target_lang: str,
    variant_key: str,
) -> None:
    """异步执行状态查询的核心逻辑。"""
    try:
        await coordinator.initialize()
        result = await coordinator.get_translation(
            project_id=project_id,
            namespace=namespace,
            keys=keys,
            target_lang=target_lang,
            variant_key=variant_key,
        )
        if result:
            console.print(
                Panel(
                    JSON(json.dumps(result)),
                    title=f"[green]✅ 找到已发布的翻译 for [bold]{target_lang}[/bold][/green]",
                    border_style="green",
                    expand=False,
                )
            )
        else:
            console.print(
                f"[yellow]⚠️ 未找到 [bold]{target_lang}[/bold] 的已发布翻译（或其回退）。"
                "请使用 `tools/inspect_db.py` 查看草稿或待审阅状态。[/yellow]"
            )
    finally:
        await coordinator.close()


@status_app.command("get")
def get_status(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Option("--project-id", help="项目/租户的唯一标识符。")],
    namespace: Annotated[str, typer.Option("--namespace", help="内容的命名空间。")],
    keys_json: Annotated[str, typer.Option("--keys-json", help="定位内容的上下文键集 (JSON 字符串)。")],
    target_lang: Annotated[str, typer.Option("--target-lang", "-t", help="目标语言代码。")],
    variant_key: Annotated[str, typer.Option("--variant", "-v", help="语言内变体。")] = '-',
) -> None:
    """根据 UIDA 查询一条已发布的翻译记录，会自动应用回退逻辑。"""
    try:
        keys = json.loads(keys_json)
    except json.JSONDecodeError as e:
        console.print(f"[bold red]❌ Keys JSON 格式错误: {e}[/bold red]")
        raise typer.Exit(code=1) from e

    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    asyncio.run(
        _get_status(coordinator, project_id, namespace, keys, target_lang, variant_key)
    )


async def _publish(coordinator: Coordinator, translation_id: str) -> None:
    try:
        await coordinator.initialize()
        success = await coordinator.publish_translation(translation_id)
        if success:
            console.print(f"[green]✅ 翻译 ID [bold]{translation_id}[/bold] 已成功发布！[/green]")
        else:
            console.print(
                f"[red]❌ 发布失败。可能是因为已有相同维度的已发布版本，"
                "或记录不存在。[/red]"
            )
    finally:
        await coordinator.close()


@status_app.command("publish")
def publish_translation(
    ctx: typer.Context,
    translation_id: Annotated[str, typer.Argument(help="要发布的翻译记录的唯一 ID。")],
) -> None:
    """将一条 'reviewed' 状态的翻译记录发布。"""
    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    asyncio.run(_publish(coordinator, translation_id))


async def _reject(coordinator: Coordinator, translation_id: str) -> None:
    try:
        await coordinator.initialize()
        success = await coordinator.reject_translation(translation_id)
        if success:
            console.print(f"[yellow]✅ 翻译 ID [bold]{translation_id}[/bold] 已被拒绝。[/yellow]")
        else:
            console.print(f"[red]❌ 操作失败。记录可能不存在。[/red]")
    finally:
        await coordinator.close()


@status_app.command("reject")
def reject_translation(
    ctx: typer.Context,
    translation_id: Annotated[str, typer.Argument(help="要拒绝的翻译记录的唯一 ID。")],
) -> None:
    """将一条翻译记录的状态设置为 'rejected'。"""
    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    asyncio.run(_reject(coordinator, translation_id))
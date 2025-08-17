# packages/server/src/trans_hub/presentation/cli/commands/status.py
"""
处理翻译状态查询和管理的 CLI 命令，包括评论功能。
"""

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from .._utils import get_coordinator
from .._state import CLISharedState
from .._shared_options import (
    PROJECT_ID_OPTION,
    NAMESPACE_OPTION,
    KEYS_JSON_OPTION,
    ACTOR_OPTION,
)  # [修改] 导入共享选项

app = typer.Typer(help="查询和管理翻译记录的状态与评论。")
console = Console()


@app.command("get")
async def get_translation(
    ctx: typer.Context,
    project_id: PROJECT_ID_OPTION,
    namespace: NAMESPACE_OPTION,
    keys_json: KEYS_JSON_OPTION,
    target_lang: Annotated[str, typer.Option("-t", help="目标语言。")],
    variant_key: Annotated[str, typer.Option("-v", help="变体键。")] = "-",
):
    """根据 UIDA 查询最终已发布的翻译，会自动应用回退逻辑。"""
    state: CLISharedState = ctx.obj
    try:
        keys = json.loads(keys_json)
    except json.JSONDecodeError as e:
        console.print(f"[bold red]❌ Keys JSON 格式错误: {e}[/bold red]")
        raise typer.Exit(code=1)

    async with get_coordinator(state) as coordinator:
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
                    Syntax(
                        json.dumps(result, indent=2, ensure_ascii=False),
                        "json",
                        theme="monokai",
                    ),
                    title="[green]✅ 已解析的翻译内容[/green]",
                    border_style="green",
                )
            )
        else:
            console.print(
                "[yellow]⚠️ 未找到该 UIDA 对应的已发布翻译（或其回退版本）。[/yellow]"
            )


@app.command("publish")
async def publish(
    ctx: typer.Context,
    revision_id: Annotated[str, typer.Argument(help="要发布的 'reviewed' 状态的翻译修订 ID。")],
    actor: ACTOR_OPTION = "cli_user",
):
    state: CLISharedState = ctx.obj
    async with get_coordinator(state) as coordinator:
        success = await coordinator.publish_translation(revision_id, actor=actor)
        if success:
            console.print(f"[green]✅ 修订 [bold]{revision_id}[/bold] 已成功发布！[/green]")
        else:
            console.print("[red]❌ 发布失败。请检查修订 ID 是否正确，且其状态为 'reviewed'。[/red]")

@app.command("unpublish")
async def unpublish(
    ctx: typer.Context,
    revision_id: Annotated[str, typer.Argument(help="要撤回发布的 'published' 状态的翻译修订 ID。")],
    actor: ACTOR_OPTION = "cli_user",
):
    """将一条 'published' 状态的翻译修订撤回，使其状态变回 'reviewed'。"""
    state: CLISharedState = ctx.obj
    async with get_coordinator(state) as coordinator:
        success = await coordinator.unpublish_translation(revision_id, actor=actor)
        if success:
            console.print(f"[green]✅ 修订 [bold]{revision_id}[/bold] 已成功撤回发布！[/green]")
        else:
            console.print("[red]❌ 撤回发布失败。请检查修订 ID 是否正确，且其状态为 'published'。[/red]")

@app.command("comments")
async def get_comments(
    ctx: typer.Context,
    head_id: Annotated[str, typer.Argument(help="要查询评论的翻译头 (Head) ID。")],
):
    """获取指定翻译头 (Head) 的所有评论。"""
    state: CLISharedState = ctx.obj
    async with get_coordinator(state) as coordinator:
        comments = await coordinator.get_comments(head_id)
        if not comments:
            console.print(f"[yellow]Head ID [bold]{head_id}[/bold] 尚无评论。[/yellow]")
            return

        table = Table(
            title=f"Comments for Head ID: {head_id}",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Author", style="cyan", width=20)
        table.add_column("Comment")
        table.add_column("Timestamp", style="dim", width=22)
        for c in comments:
            # Ensure created_at is not None before formatting
            timestamp_str = str(c.created_at) if c.created_at else "N/A"
            table.add_row(c.author, c.body, timestamp_str)
        console.print(table)


@app.command("comment")
async def add_comment(
    ctx: typer.Context,
    head_id: Annotated[str, typer.Argument(help="要评论的翻译头的 ID。")],
    body: Annotated[str, typer.Argument(help="评论内容。")],
    author: Annotated[
        str, typer.Option("--author", "-a", help="评论者名称。")
    ] = "cli_user",
):
    """为指定的翻译头 (Head) 添加一条评论。"""
    state: CLISharedState = ctx.obj
    if not body.strip():
        console.print("[red]❌ 评论内容不能为空。[/red]")
        raise typer.Exit(code=1)

    async with get_coordinator(state) as coordinator:
        try:
            comment_id = await coordinator.add_comment(head_id, author, body)
            console.print(f"[green]✅ 评论已添加！[/green] Comment ID: {comment_id}")
        except ValueError as e:
            console.print(f"[red]❌ 操作失败: {e}[/red]")
            raise typer.Exit(code=1)

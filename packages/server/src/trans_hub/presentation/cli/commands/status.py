# packages/server/src/trans_hub/presentation/cli/commands/status.py
"""
处理翻译状态查询和管理的 CLI 命令，包括评论功能。
"""

import asyncio
import json
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from trans_hub.application.coordinator import Coordinator
from ..main import CLISharedState

app = typer.Typer(help="查询和管理翻译记录的状态与评论。")
console = Console()

# --- 辅助函数 ---


async def _get_head_id_from_uida(
    coordinator: Coordinator,
    project_id: str,
    namespace: str,
    keys: dict,
    target_lang: str,
    variant_key: str,
) -> str | None:
    """通过 UIDA 查找 Head ID。"""
    head = await coordinator.handler.get_translation_head_by_uida(
        project_id=project_id,
        namespace=namespace,
        keys=keys,
        target_lang=target_lang,
        variant_key=variant_key,
    )
    return head.id if head else None


# --- 命令实现 ---


@app.command("get")
def get_translation(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Option("-p", help="项目 ID。")],
    namespace: Annotated[str, typer.Option("-n", help="命名空间。")],
    keys_json: Annotated[str, typer.Option("-k", help="Keys JSON。")],
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

    async def _run():
        coordinator = Coordinator(state.config)
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
                        JSON(json.dumps(result, indent=2, ensure_ascii=False)),
                        title="[green]✅ 已解析的翻译内容[/green]",
                        border_style="green",
                    )
                )
            else:
                console.print(
                    "[yellow]⚠️ 未找到该 UIDA 对应的已发布翻译（或其回退版本）。[/yellow]"
                )
        finally:
            await coordinator.close()

    asyncio.run(_run())


@app.command("publish")
def publish(
    ctx: typer.Context,
    revision_id: Annotated[
        str, typer.Argument(help="要发布的 'reviewed' 状态的翻译修订 ID。")
    ],
    actor: Annotated[str, typer.Option("--actor", help="操作者身份。")] = "cli_user",
):
    """将一条 'reviewed' 状态的翻译修订发布为最新版本。"""
    state: CLISharedState = ctx.obj

    async def _run():
        coordinator = Coordinator(state.config)
        try:
            await coordinator.initialize()
            success = await coordinator.publish_translation(revision_id, actor=actor)
            if success:
                console.print(
                    f"[green]✅ 修订 [bold]{revision_id}[/bold] 已成功发布！[/green]"
                )
            else:
                console.print(
                    "[red]❌ 发布失败。请检查修订 ID 是否正确，且其状态为 'reviewed'。[/red]"
                )
        finally:
            await coordinator.close()

    asyncio.run(_run())


@app.command("comments")
def get_comments(
    ctx: typer.Context,
    head_id: Annotated[str, typer.Argument(help="要查询评论的翻译头 (Head) ID。")],
):
    """获取指定翻译头 (Head) 的所有评论。"""
    state: CLISharedState = ctx.obj

    async def _run():
        coordinator = Coordinator(state.config)
        try:
            await coordinator.initialize()
            comments = await coordinator.get_comments(head_id)
            if not comments:
                console.print(
                    f"[yellow]Head ID [bold]{head_id}[/bold] 尚无评论。[/yellow]"
                )
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
                table.add_row(c.author, c.body, str(c.created_at))
            console.print(table)
        finally:
            await coordinator.close()

    asyncio.run(_run())


@app.command("comment")
def add_comment(
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

    async def _run():
        coordinator = Coordinator(state.config)
        try:
            await coordinator.initialize()
            comment_id = await coordinator.add_comment(head_id, author, body)
            console.print(f"[green]✅ 评论已添加！[/green] Comment ID: {comment_id}")
        except ValueError as e:
            console.print(f"[red]❌ 操作失败: {e}[/red]")
            raise typer.Exit(code=1)
        finally:
            await coordinator.close()

    asyncio.run(_run())

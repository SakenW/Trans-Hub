# packages/server/src/trans_hub/adapters/cli/commands/status.py
"""
处理翻译状态查询和管理的 CLI 命令，包括发布、撤回、拒绝和评论功能。
"""

import json
from typing import Annotated

import typer
from dependency_injector.wiring import Provide, inject
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from trans_hub.adapters.cli._shared_options import (
    ACTOR_OPTION,
    KEYS_JSON_OPTION,
    NAMESPACE_OPTION,
    PROJECT_ID_OPTION,
)
from trans_hub.application.coordinator import Coordinator
from trans_hub.di.container import AppContainer

app = typer.Typer(help="查询和管理翻译记录的状态与生命周期。", no_args_is_help=True)
console = Console()


# --- Logic Functions ---

@inject
async def _get_translation_logic(
    project_id: str,
    namespace: str,
    keys: dict,
    target_lang: str,
    variant_key: str,
    coordinator: Coordinator = Provide[AppContainer.coordinator],
):
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


@inject
async def _publish_logic(
    revision_id: str,
    actor: str,
    coordinator: Coordinator = Provide[AppContainer.coordinator],
):
    success = await coordinator.publish_translation(revision_id, actor=actor)
    if success:
        console.print(
            f"[green]✅ 修订 [bold]{revision_id}[/bold] 已成功发布！[/green]"
        )
    else:
        console.print(
            "[red]❌ 发布失败。请检查修订 ID 是否正确，且其状态为 'reviewed'。[/red]"
        )


@inject
async def _unpublish_logic(
    revision_id: str,
    actor: str,
    coordinator: Coordinator = Provide[AppContainer.coordinator],
):
    success = await coordinator.unpublish_translation(revision_id, actor=actor)
    if success:
        console.print(
            f"[yellow]✅ 修订 [bold]{revision_id}[/bold] 的发布已被撤回。[/yellow]"
        )
    else:
        console.print(
            "[red]❌ 撤回失败。请检查修订 ID 是否正确，且其状态为 'published'。[/red]"
        )


@inject
async def _reject_logic(
    revision_id: str,
    actor: str,
    coordinator: Coordinator = Provide[AppContainer.coordinator],
):
    success = await coordinator.reject_translation(revision_id, actor=actor)
    if success:
        console.print(
            f"[yellow]✅ 修订 [bold]{revision_id}[/bold] 已被标记为 'rejected'。[/yellow]"
        )
    else:
        console.print("[red]❌ 拒绝失败。请检查修订 ID 是否正确。[/red]")


@inject
async def _get_comments_logic(
    head_id: str,
    coordinator: Coordinator = Provide[AppContainer.coordinator],
):
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
        timestamp_str = (
            str(c.created_at.strftime("%Y-%m-%d %H:%M:%S %Z"))
            if c.created_at
            else "N/A"
        )
        table.add_row(c.author, c.body, timestamp_str)
    console.print(table)


@inject
async def _add_comment_logic(
    head_id: str,
    author: str,
    body: str,
    coordinator: Coordinator = Provide[AppContainer.coordinator],
):
    try:
        comment_id = await coordinator.add_comment(head_id, author, body)
        console.print(f"[green]✅ 评论已添加！[/green] Comment ID: {comment_id}")
    except ValueError as e:
        console.print(f"[red]❌ 操作失败: {e}[/red]")
        raise typer.Exit(code=1)


# --- CLI Functions ---

@app.command("get")
async def get_translation_cli(
    project_id: PROJECT_ID_OPTION,
    namespace: NAMESPACE_OPTION,
    keys_json: KEYS_JSON_OPTION,
    target_lang: Annotated[str, typer.Option("-t", "--target-lang", help="目标语言。")],
    variant_key: Annotated[str, typer.Option("-v", "--variant", help="变体键。")] = "-",
):
    """根据 UIDA 查询最终已发布的翻译，会自动应用回退逻辑。"""
    try:
        keys = json.loads(keys_json)
    except json.JSONDecodeError as e:
        console.print(f"[bold red]❌ Keys JSON 格式错误: {e}[/bold red]")
        raise typer.Exit(code=1)

    await _get_translation_logic(
        project_id=project_id,
        namespace=namespace,
        keys=keys,
        target_lang=target_lang,
        variant_key=variant_key,
    )


@app.command("publish")
async def publish_cli(
    revision_id: Annotated[
        str, typer.Argument(help="要发布的 'reviewed' 状态的翻译修订 ID。")
    ],
    actor: ACTOR_OPTION = "cli_user",
):
    """将一条 'reviewed' 状态的翻译修订发布为最新版本。"""
    await _publish_logic(revision_id=revision_id, actor=actor)


@app.command("unpublish")
async def unpublish_cli(
    revision_id: Annotated[
        str, typer.Argument(help="要撤回发布的 'published' 状态的翻译修订 ID。")
    ],
    actor: ACTOR_OPTION = "cli_admin",
):
    """[新增] 撤回一个已发布的修订，使其状态回退到 'reviewed'。"""
    await _unpublish_logic(revision_id=revision_id, actor=actor)


@app.command("reject")
async def reject_cli(
    revision_id: Annotated[str, typer.Argument(help="要拒绝的翻译修订 ID。")],
    actor: ACTOR_OPTION = "cli_reviewer",
):
    """[新增] 将一条翻译修订的状态标记为 'rejected'。"""
    await _reject_logic(revision_id=revision_id, actor=actor)


@app.command("comments")
async def get_comments_cli(
    head_id: Annotated[str, typer.Argument(help="要查询评论的翻译头 (Head) ID。")],
):
    """获取指定翻译头 (Head) 的所有评论。"""
    await _get_comments_logic(head_id=head_id)


@app.command("comment")
async def add_comment_cli(
    head_id: Annotated[str, typer.Argument(help="要评论的翻译头的 ID。")],
    body: Annotated[str, typer.Argument(help="评论内容。")],
    author: ACTOR_OPTION = "cli_user",
):
    """为指定的翻译头 (Head) 添加一条评论。"""
    if not body.strip():
        console.print("[red]❌ 评论内容不能为空。[/red]")
        raise typer.Exit(code=1)
    await _add_comment_logic(head_id=head_id, author=author, body=body)

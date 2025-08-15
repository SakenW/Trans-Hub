# packages/server/src/trans_hub/presentation/cli/commands/request.py
"""
处理翻译请求提交的 CLI 命令。
"""

import asyncio
import json
from typing import Annotated, TYPE_CHECKING

import typer
from rich.console import Console

from trans_hub.application.coordinator import Coordinator

# 在类型检查时导入 CLISharedState
if TYPE_CHECKING:
    from ..main import CLISharedState

app = typer.Typer(help="提交和管理翻译请求。")
console = Console()


@app.command("new")
def request_new(
    ctx: typer.Context,
    project_id: Annotated[
        str, typer.Option("--project-id", "-p", help="项目/租户的唯一标识符。")
    ],
    namespace: Annotated[
        str,
        typer.Option("--namespace", "-n", help="内容的命名空间，如 'ui.buttons.v1'。"),
    ],
    keys_json: Annotated[
        str,
        typer.Option("--keys", "-k", help="定位内容的最小上下文键集 (JSON 字符串)。"),
    ],
    source_payload_json: Annotated[
        str, typer.Option("--payload", "-d", help="要翻译的源内容 (JSON 字符串)。")
    ],
    target_langs: Annotated[
        list[str],
        typer.Option("--target", "-t", help="一个或多个目标语言代码 (可多次使用)。"),
    ],
    source_lang: Annotated[
        str | None,
        typer.Option("--source", "-s", help="源语言代码 (可选，若配置中已提供)。"),
    ] = None,
    variant_key: Annotated[
        str, typer.Option("--variant", "-v", help="语言内变体 (可选)。")
    ] = "-",
    actor: Annotated[str, typer.Option("--actor", help="操作者身份。")] = "cli_user",
) -> None:
    """
    向 Trans-Hub 提交一个新的 UIDA 翻译请求。
    """
    state: "CLISharedState" = ctx.obj

    try:
        keys = json.loads(keys_json)
        source_payload = json.loads(source_payload_json)
    except json.JSONDecodeError as e:
        console.print(f"[bold red]❌ JSON 格式错误: {e}[/bold red]")
        raise typer.Exit(code=1)

    if not target_langs:
        console.print("[bold red]❌ 错误: 必须至少提供一个 --target 语言。[/bold red]")
        raise typer.Exit(code=1)

    final_source_lang = source_lang or state.config.default_source_lang
    if not final_source_lang:
        console.print(
            "[bold red]❌ 错误: 必须通过 --source 或在配置中提供源语言。[/bold red]"
        )
        raise typer.Exit(code=1)

    console.print("[cyan]正在提交翻译请求...[/cyan]")

    async def _run():
        coordinator = Coordinator(state.config)
        try:
            await coordinator.initialize()
            content_id = await coordinator.request_translation(
                project_id=project_id,
                namespace=namespace,
                keys=keys,
                source_payload=source_payload,
                target_langs=target_langs,
                source_lang=final_source_lang,
                variant_key=variant_key,
                actor=actor,
            )
            console.print("[bold green]✅ 翻译请求已成功提交！[/bold green]")
            console.print(f"  - [dim]内容 ID (Content ID):[/dim] {content_id}")
            console.print("  - [dim]TM 未命中时，任务已加入后台队列等待处理。[/dim]")
        finally:
            await coordinator.close()

    try:
        asyncio.run(_run())
    except Exception as e:
        console.print(f"[bold red]❌ 请求处理时发生意外错误: {e}[/bold red]")
        console.print_exception(show_locals=True)
        raise typer.Exit(code=1)

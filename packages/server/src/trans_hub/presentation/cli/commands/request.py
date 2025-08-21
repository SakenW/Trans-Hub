# packages/server/src/trans_hub/presentation/cli/commands/request.py
import json
from typing import Annotated

import typer
from rich.console import Console
from dependency_injector.wiring import inject, Provide

from trans_hub.application.coordinator import Coordinator
from trans_hub.config import TransHubConfig
from trans_hub.containers import ApplicationContainer
from .._shared_options import (
    ACTOR_OPTION,
    KEYS_JSON_OPTION,
    NAMESPACE_OPTION,
    PROJECT_ID_OPTION,
)

app = typer.Typer(help="提交和管理翻译请求。")
console = Console()


@app.command("new")
@inject
async def request_new(
    ctx: typer.Context,
    project_id: PROJECT_ID_OPTION,
    namespace: NAMESPACE_OPTION,
    keys_json: KEYS_JSON_OPTION,
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
    actor: ACTOR_OPTION = "cli_user",
    coordinator: Coordinator = Provide[ApplicationContainer.services.coordinator],
    config: TransHubConfig = Provide[ApplicationContainer.pydantic_config],
) -> None:
    """
    向 Trans-Hub 提交一个新的 UIDA 翻译请求。
    """
    try:
        keys = json.loads(keys_json)
        source_payload = json.loads(source_payload_json)
    except json.JSONDecodeError as e:
        console.print(f"[bold red]❌ JSON 格式错误: {e}[/bold red]")
        raise typer.Exit(code=1)

    if not target_langs:
        console.print("[bold red]❌ 错误: 必须至少提供一个 --target 语言。[/bold red]")
        raise typer.Exit(code=1)

    console.print("[cyan]正在提交翻译请求...[/cyan]")

    final_source_lang = source_lang or config.default_source_lang
    if not final_source_lang:
        console.print(
            "[bold red]❌ 错误: 必须通过 --source 或在配置中提供源语言。[/bold red]"
        )
        raise typer.Exit(code=1)

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

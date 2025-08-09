# trans_hub/cli/request.py
# [v2.4 Refactor] 更新 'request new' 命令以使用 UIDA 参数。
import asyncio
import json
from typing import Annotated, Any

import typer
from rich.console import Console

from trans_hub.cli.state import State
from trans_hub.cli.utils import create_coordinator
from trans_hub.coordinator import Coordinator
from trans_hub.utils import validate_lang_codes

console = Console()
request_app = typer.Typer(help="提交和管理翻译请求 (UIDA 模式)")


async def _async_request_new(coordinator: Coordinator, request_data: dict[str, Any]) -> None:
    try:
        await coordinator.initialize()
        await coordinator.request(**request_data)
        console.print("[bold green]✅ 翻译请求已成功提交！[/bold green]")
        console.print("[dim]（TM 命中则直接完成，否则已加入后台队列）[/dim]")
    finally:
        await coordinator.close()


@request_app.command("new")
def request_new(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Option("--project-id", help="项目/租户的唯一标识符。")],
    namespace: Annotated[str, typer.Option("--namespace", help="内容的命名空间，如 'ui.buttons.v1'。")],
    keys_json: Annotated[str, typer.Option("--keys-json", help="定位内容的最小上下文键集 (JSON 字符串)。")],
    source_payload_json: Annotated[str, typer.Option("--source-payload-json", help="要翻译的源内容 (JSON 字符串)。")],
    target_langs: Annotated[list[str], typer.Option("--target", "-t", help="一个或多个目标语言代码。")],
    source_lang: Annotated[str | None, typer.Option("--source-lang", "-s", help="源语言代码 (可选，若配置中已提供)。")] = None,
    variant_key: Annotated[str, typer.Option("--variant", help="语言内变体 (可选)。")] = '-',
) -> None:
    """向 Trans-Hub 提交一个新的 UIDA 翻译请求。"""
    try:
        keys = json.loads(keys_json)
        source_payload = json.loads(source_payload_json)
    except json.JSONDecodeError as e:
        console.print(f"[bold red]❌ JSON 格式错误: {e}[/bold red]")
        raise typer.Exit(code=1)

    state: State = ctx.obj
    request_data = {
        "project_id": project_id, "namespace": namespace, "keys": keys,
        "source_payload": source_payload, "target_langs": target_langs,
        "source_lang": source_lang or state.config.source_lang, "variant_key": variant_key
    }
    
    if not request_data["source_lang"]:
         console.print("[bold red]❌ 必须通过 --source-lang 或 TH_SOURCE_LANG 提供源语言。[/bold red]")
         raise typer.Exit(code=1)

    coordinator = create_coordinator(state.config)
    asyncio.run(_async_request_new(coordinator, request_data))
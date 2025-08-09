# trans_hub/cli/request.py
"""处理翻译请求提交的 CLI 命令 (UIDA 架构版)。"""

import asyncio
import json
from typing import Annotated, Any

import typer
from rich.console import Console

from trans_hub._uida.encoder import CanonicalizationError
from trans_hub.cli.state import State
from trans_hub.cli.utils import create_coordinator
from trans_hub.coordinator import Coordinator
from trans_hub.utils import validate_lang_codes

console = Console()
request_app = typer.Typer(help="提交和管理翻译请求 (UIDA 模式)")


async def _async_request_new(
    coordinator: Coordinator,
    project_id: str,
    namespace: str,
    keys: dict[str, Any],
    source_payload: dict[str, Any],
    source_lang: str,
    target_langs: list[str],
) -> None:
    """异步执行 UIDA 请求的核心逻辑。"""
    try:
        await coordinator.initialize()
        await coordinator.request(
            project_id=project_id,
            namespace=namespace,
            keys=keys,
            source_payload=source_payload,
            source_lang=source_lang,
            target_langs=target_langs,
        )
        console.print("[bold green]✅ 翻译请求已成功处理！[/bold green]")
        console.print("[dim]（TM 命中则直接完成，否则已加入后台队列）[/dim]")
    finally:
        await coordinator.close()


@request_app.command("new")
def request_new(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Option("--project-id", help="项目/租户的唯一标识符。")],
    namespace: Annotated[str, typer.Option("--namespace", help="内容的命名空间，如 'ui.buttons.v1'。")],
    keys_json: Annotated[
        str, typer.Option("--keys-json", help="定位内容的最小上下文键集 (JSON 字符串)。")
    ],
    source_payload_json: Annotated[
        str, typer.Option("--source-payload-json", help="要翻译的源内容 (JSON 字符串)。")
    ],
    source_lang: Annotated[str, typer.Option("--source-lang", "-s", help="源语言代码。")],
    target_langs: Annotated[
        list[str], typer.Option("--target", "-t", help="一个或多个目标语言代码。")
    ],
) -> None:
    """向 Trans-Hub 提交一个新的 UIDA 翻译请求。"""
    # 1. 输入校验
    try:
        validate_lang_codes([source_lang])
        validate_lang_codes(target_langs)
    except ValueError as e:
        console.print(f"[bold red]❌ 语言代码错误: {e}[/bold red]")
        raise typer.Exit(code=1) from e

    try:
        keys = json.loads(keys_json)
        if not isinstance(keys, dict):
            raise TypeError("Keys 必须是一个 JSON 对象。")
        source_payload = json.loads(source_payload_json)
        if not isinstance(source_payload, dict):
            raise TypeError("Source Payload 必须是一个 JSON 对象。")
    except (json.JSONDecodeError, TypeError) as e:
        console.print(f"[bold red]❌ JSON 格式错误: {e}[/bold red]")
        raise typer.Exit(code=1) from e

    # 2. 执行业务逻辑
    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    console.print(f"正在为 UIDA 提交翻译请求...")
    console.print(f"[cyan]  Project: {project_id}[/cyan]")
    console.print(f"[cyan]  Namespace: {namespace}[/cyan]")

    try:
        asyncio.run(
            _async_request_new(
                coordinator,
                project_id,
                namespace,
                keys,
                source_payload,
                source_lang,
                target_langs,
            )
        )
    except CanonicalizationError as e:
        console.print(f"[bold red]❌ UIDA 规范化错误: {e}[/bold red]")
        console.print("[dim]请检查 keys-json 是否符合 I-JSON 规范（如，不包含浮点数）。[/dim]")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[bold red]❌ 请求处理失败: {e}[/bold red]")
        logger.exception("详细错误信息")
        raise typer.Exit(code=1) from e
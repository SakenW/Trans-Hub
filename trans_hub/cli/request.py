# trans_hub/cli/request.py
"""
处理翻译请求提交的 CLI 命令。
v3.0.0 重大更新：命令接口已重构，以适配基于业务ID和结构化载荷的新架构。
"""

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
request_app = typer.Typer(help="提交和管理翻译请求")


async def _async_request_new(
    coordinator: Coordinator,
    business_id: str,
    source_payload: dict[str, Any],
    target_langs: list[str],
    source_lang: str | None,
    force: bool,
    context: dict[str, Any] | None,
) -> None:
    """异步执行请求的核心逻辑。"""
    try:
        await coordinator.initialize()
        await coordinator.request(
            business_id=business_id,
            source_payload=source_payload,
            target_langs=target_langs,
            source_lang=source_lang,
            force_retranslate=force,
            context=context,
        )
        console.print("[bold green]✅ 翻译请求已成功加入队列！[/bold green]")
    finally:
        await coordinator.close()


@request_app.command("new")
def request_new(
    ctx: typer.Context,
    business_id: Annotated[
        str, typer.Option("--id", help="关联内容的、全局唯一的业务ID (必需)。")
    ],
    payload_json: Annotated[
        str,
        typer.Option(
            "--payload-json",
            help=(
                '要翻译的结构化内容，格式为 JSON 字符串 (必需)。例如: \'{"text": "Hello"}\''
            ),
        ),
    ],
    target_lang: Annotated[
        list[str],
        typer.Option(
            "--target", "-t", help="一个或多个目标语言代码 (例如: de, fr, zh-CN)。"
        ),
    ],
    source_lang: Annotated[
        str | None,
        typer.Option(
            "--source", "-s", help="源语言代码 (可选，若不提供则使用引擎默认值)。"
        ),
    ] = None,
    context_json: Annotated[
        str | None,
        typer.Option(
            "--context-json",
            help="与请求相关的上下文，格式为 JSON 字符串 (可选)。",
        ),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="强制重新翻译，即使已存在有效的翻译。")
    ] = False,
) -> None:
    """向 Trans-Hub 提交一个新的翻译请求。"""
    # 1. 输入校验
    try:
        validate_lang_codes(target_lang)
        if source_lang:
            validate_lang_codes([source_lang])
    except ValueError as e:
        console.print(f"[bold red]❌ 语言代码错误: {e}[/bold red]")
        raise typer.Exit(code=1) from e

    try:
        source_payload = json.loads(payload_json)
        if not isinstance(source_payload, dict):
            raise TypeError("Payload 必须是一个 JSON 对象。")
    except (json.JSONDecodeError, TypeError) as e:
        console.print(f"[bold red]❌ Payload 格式错误: {e}[/bold red]")
        raise typer.Exit(code=1) from e

    context: dict[str, Any] | None = None
    if context_json:
        try:
            context = json.loads(context_json)
            if not isinstance(context, dict):
                raise TypeError("Context 必须是一个 JSON 对象。")
        except (json.JSONDecodeError, TypeError) as e:
            console.print(f"[bold red]❌ Context 格式错误: {e}[/bold red]")
            raise typer.Exit(code=1) from e

    # 2. 执行业务逻辑
    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    console.print(f"正在为业务ID [bold cyan]{business_id}[/bold cyan] 提交翻译请求...")

    try:
        asyncio.run(
            _async_request_new(
                coordinator,
                business_id,
                source_payload,
                target_lang,
                source_lang,
                force,
                context,
            )
        )
    except Exception as e:
        console.print(f"[bold red]❌ 请求处理失败: {e}[/bold red]")
        raise typer.Exit(code=1) from e

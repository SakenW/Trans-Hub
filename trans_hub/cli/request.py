# trans_hub/cli/request.py
"""处理翻译请求提交的 CLI 命令。"""

import asyncio
from typing import Optional

import typer
from rich.console import Console

from trans_hub.cli.state import State
from trans_hub.cli.utils import create_coordinator
from trans_hub.coordinator import Coordinator
from trans_hub.utils import validate_lang_codes

console = Console()
request_app = typer.Typer(help="提交翻译请求")


async def _async_request_new(
    coordinator: Coordinator,
    text: str,
    target_lang: list[str],
    source_lang: Optional[str],
    business_id: Optional[str],
    force: bool,
) -> None:
    """异步执行请求的核心逻辑。"""
    try:
        await coordinator.initialize()
        await coordinator.request(
            text_content=text,
            target_langs=target_lang,
            source_lang=source_lang,
            business_id=business_id,
            force_retranslate=force,
        )
        console.print("[bold green]✅ 翻译请求已成功加入队列！[/bold green]")
    finally:
        await coordinator.close()


@request_app.command("new")
def request_new(
    ctx: typer.Context,
    text: str = typer.Argument(..., help="要翻译的文本内容。"),
    target_lang: list[str] = typer.Option(
        ..., "--target", "-t", help="一个或多个目标语言代码 (例如: de, fr, zh-CN)。"
    ),
    source_lang: Optional[str] = typer.Option(
        None, "--source", "-s", help="源语言代码 (可选，若不提供则使用引擎默认值)。"
    ),
    business_id: Optional[str] = typer.Option(
        None, "--id", help="关联的业务ID，用于跟踪任务状态 (可选)。"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="强制重新翻译，即使已存在有效的翻译。"
    ),
) -> None:
    """
    向 Trans-Hub 提交一个新的翻译请求。
    """
    try:
        validate_lang_codes(target_lang)
        if source_lang:
            validate_lang_codes([source_lang])
    except ValueError as e:
        console.print(f"[bold red]❌ 语言代码错误: {e}[/bold red]")
        raise typer.Exit(code=1)

    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    console.print(f"正在提交翻译请求: [dim]'{text[:50]}...'[/dim]")
    try:
        # v3.1 最终决定：不再支持旧版 Python，直接使用 asyncio.run
        asyncio.run(
            _async_request_new(
                coordinator, text, target_lang, source_lang, business_id, force
            )
        )
    except Exception as e:
        console.print(f"[bold red]❌ 请求处理失败: {e}[/bold red]")
        raise typer.Exit(code=1)

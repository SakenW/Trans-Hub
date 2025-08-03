# trans_hub/cli/request/main.py
"""
Trans-Hub Request CLI 子模块。
"""

import asyncio
from typing import List, Optional

import structlog
from rich.console import Console

from trans_hub.coordinator import Coordinator

log = structlog.get_logger("trans_hub.cli.request")
console = Console()


async def _async_request(
    coordinator: Coordinator,
    text: str,
    target_lang: List[str],
    source_lang: Optional[str],
    business_id: Optional[str],
    force: bool,
) -> None:
    """
    异步提交翻译请求的内部函数。
    """
    log.info("收到新的翻译请求...", text=text, targets=target_lang, force=force)
    await coordinator.request(
        text_content=text,
        target_langs=target_lang,
        source_lang=source_lang,
        business_id=business_id,
        force_retranslate=force,
    )
    console.print("[green]✅ 翻译请求已成功提交！[/green]")


def request(
    coordinator: Coordinator,
    loop: asyncio.AbstractEventLoop,
    text: str,
    target_lang: List[str],
    source_lang: Optional[str] = None,
    business_id: Optional[str] = None,
    force: bool = False,
) -> None:
    """
    提交一个新的翻译请求到队列中。
    """
    try:
        loop.run_until_complete(
            _async_request(
                coordinator, text, target_lang, source_lang, business_id, force
            )
        )
        log.info("翻译请求处理完成")
    except Exception as e:
        log.error("请求处理失败", error=str(e), exc_info=True)
        raise SystemExit(1)
    finally:
        # 确保协调器已关闭
        if coordinator:
            log.info("请求处理完成，正在关闭协调器...")
            loop.run_until_complete(coordinator.close())
            log.info("协调器已关闭")
            loop.close()
            # 重置全局状态以便后续命令可重新初始化
            try:
                import trans_hub.cli as cli_main

                cli_main._coordinator = None
                cli_main._loop = None
            except Exception:
                pass

# trans_hub/cli/worker/main.py
"""
Trans-Hub Worker CLI 子模块。
"""

import asyncio
import signal
from typing import Any, List

import structlog

from trans_hub.coordinator import Coordinator
from trans_hub.types import TranslationStatus

log = structlog.get_logger("trans_hub.cli.worker")


def run_worker(
    coordinator: Coordinator,
    loop: asyncio.AbstractEventLoop,
    shutdown_event: asyncio.Event,
    lang: List[str],
    batch_size: int = 50,
    polling_interval: int = 5,
) -> None:
    """
    启动一个或多个后台工作进程，持续处理待翻译任务。
    """
    log.info(
        "启动 Worker...",
        target_languages=lang,
        batch_size=batch_size,
        polling_interval=polling_interval,
    )

    def signal_handler(signum: int, frame: Any) -> None:
        """信号处理函数。"""
        log.info("收到信号，正在触发优雅停机...", signal=signum)
        if shutdown_event:
            # 使用call_soon_threadsafe确保线程安全
            loop.call_soon_threadsafe(shutdown_event.set)
        else:
            log.warning("关闭事件未初始化，无法触发优雅停机")

    # 注册信号处理器
    loop.add_signal_handler(signal.SIGTERM, signal_handler, signal.SIGTERM, None)
    loop.add_signal_handler(signal.SIGINT, signal_handler, signal.SIGINT, None)

    async def process_language(target_lang: str) -> None:
        """处理单一语言的循环。"""
        # 确保关闭事件已初始化
        if not shutdown_event:
            log.error("关闭事件未初始化，无法启动工作进程")
            return

        while not shutdown_event.is_set():
            try:
                processed_count = 0
                async for result in coordinator.process_pending_translations(
                    target_lang, batch_size
                ):
                    # 检查是否收到停止信号
                    if shutdown_event.is_set():
                        break

                    processed_count += 1
                    if result.status == TranslationStatus.TRANSLATED:
                        log.info(
                            "翻译成功",
                            lang=target_lang,
                            original=f"'{result.original_content[:20]}...'",
                        )
                    else:
                        log.warning(
                            "翻译失败",
                            lang=target_lang,
                            original=f"'{result.original_content[:20]}...'",
                            error=result.error,
                        )

                # 如果没有处理任何任务，休眠一段时间
                if processed_count == 0:
                    log.debug(
                        "队列为空，休眠...", lang=target_lang, interval=polling_interval
                    )
                    try:
                        await asyncio.wait_for(
                            shutdown_event.wait(), timeout=polling_interval
                        )
                    except asyncio.TimeoutError:
                        pass  # 正常超时，继续下一轮循环
            except asyncio.CancelledError:
                log.info("Worker 收到停止信号，正在退出...", lang=target_lang)
                break
            except Exception:
                log.error(
                    "Worker 循环中发生未知错误，将在5秒后重试...",
                    lang=target_lang,
                    exc_info=True,
                )
                # 等待5秒或直到收到停止信号
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass  # 正常超时，继续下一轮循环

    # 运行worker任务直到收到停机信号
    # 创建worker任务并包装成asyncio.Task对象
    worker_tasks = [
        asyncio.create_task(process_language(target_lang)) for target_lang in lang
    ]
    log.info(f"创建了 {len(worker_tasks)} 个worker任务")

    # 为每个worker任务添加异常处理包装
    async def safe_process(task: asyncio.Task[None]) -> bool:
        try:
            await task
            return True
        except asyncio.CancelledError:
            log.info("Worker 任务被取消")
            return False
        except Exception as e:
            log.error(f"Worker 任务执行异常: {e}", exc_info=True)
            return False

    # 包装所有worker任务
    safe_tasks = [safe_process(task) for task in worker_tasks]

    try:
        # 使用asyncio.gather运行所有安全包装的任务
        results = loop.run_until_complete(asyncio.gather(*safe_tasks))
        log.info(f"所有worker任务已完成，成功: {sum(results)}/{len(results)}")
    except Exception as e:
        log.error(f"worker任务集合执行异常: {e}", exc_info=True)

    # 确保所有任务都已完成或被取消
    async def cancel_pending_tasks() -> None:
        pending_tasks = asyncio.all_tasks()
        current_task = asyncio.current_task()
        tasks_to_cancel = [t for t in pending_tasks if t is not current_task]
        if tasks_to_cancel:
            log.info(f"仍有 {len(tasks_to_cancel)} 个未完成的任务，正在取消...")
            for task in tasks_to_cancel:
                task.cancel()
            for task in tasks_to_cancel:
                try:
                    await task
                    log.info(f"任务 {task} 已完成")
                except asyncio.CancelledError:
                    log.info(f"任务 {task} 已取消")
                except Exception as e:
                    log.error(
                        f"任务 {task} 取消时发生异常: {e}",
                        exc_info=True,
                    )

    loop.run_until_complete(cancel_pending_tasks())

    # 执行协调器的优雅关闭
    log.info("Worker 任务已完成，正在关闭协调器...")
    try:
        loop.run_until_complete(coordinator.close())
        log.info("协调器已成功关闭")
    except Exception as e:
        log.error(f"关闭协调器时发生异常: {e}", exc_info=True)

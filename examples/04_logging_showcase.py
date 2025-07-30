# examples/04_logging_showcase.py
"""Trans-Hub 日志系统功能与样式展示。"""

# --- 最终修复：将 sys.path hack 放在顶部，并为后续导入添加 noqa: E402 ---
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 1. 第三方库导入
import structlog  # noqa: E402

# 2. 本项目库导入
from trans_hub.logging_config import setup_logging  # noqa: E402


def showcase_logging() -> None:
    """执行日志展示的核心函数。"""
    setup_logging(log_level="DEBUG", log_format="console")
    logger = structlog.get_logger("showcase")

    print("\n--- 日志展示开始 ---\n")

    logger.debug("这是一条简单的调试信息。")
    logger.info("用户已登录。", user_id="admin", session_id="xyz123")
    logger.warning(
        "数据库连接池即将耗尽。",
        pool_size=10,
        active_connections=9,
        source="db_pool_monitor",
    )
    logger.error(
        "任务处理失败。",
        task_id="task-8f8we9",
        error_code="E502",
        details="上游服务无响应。",
    )
    logger.critical(
        "核心服务已停止响应！", system_component="AuthenticationService", status="DOWN"
    )

    try:
        1 / 0  # noqa: B018 - 我们在此处明确需要触发异常以进行测试
    except Exception as e:
        logger.exception("发生了一个可预见的异常。", error_details=str(e))

    print("\n--- 日志展示完成 ---\n")


if __name__ == "__main__":
    showcase_logging()

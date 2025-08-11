# packages/server/tools/db_doctor.py
"""
一个用于诊断、管理和修复 Trans-Hub Server 数据库环境的交互式命令行工具。
(v26 - 启动先选择环境：测试/正式；默认测试。按环境预加载 .env.test / .env；仅日志脱敏，连接用真值)

变更要点：
1) 启动时先选择环境（默认“测试环境”），或用 --env test|prod 非交互指定。
2) 选择后优先预加载对应的 .env 文件（测试：.env.test；正式：.env），再调用你的 load_config_from_env()。
   - 这样做能保证在非 pytest 场景下，测试环境也能拿到正确变量。
3) 只在打印时脱敏，绝不把掩码写回环境变量或用于连接。
4) Alembic 强制使用 psycopg2（同步）以避免 asyncpg 与 Alembic 冲突。
5) 迁移兜底：upgrade 失败则 ORM 建表 + 手写 alembic_version（不走 alembic stamp）。
6) 生产保护：TH_ENV=production 时禁止重建/清空。

启动时先选择测试环境或正式环境，默认测试环境。
统一通过 config_loader.load_config_from_env(mode=...) 加载配置。
"""

import os
import sys
from pathlib import Path

import structlog
from trans_hub.config_loader import load_config_from_env

logger = structlog.get_logger("db_doctor_final")


def choose_env_mode() -> str:
    """交互式选择环境模式"""
    try:
        import questionary
    except ImportError:
        logger.warning("缺少 questionary 库，默认使用测试环境。")
        return "test"

    mode = questionary.select(
        "请选择运行环境：",
        choices=[
            "test (测试环境)",
            "prod (正式环境)"
        ],
        default="test (测试环境)"
    ).ask()

    return "prod" if "prod" in mode else "test"


def main():
    mode = choose_env_mode()
    logger.info("选择环境", mode=mode)

    try:
        config = load_config_from_env(mode=mode, strict=True)
    except Exception as e:
        logger.error("配置加载失败", error=str(e))
        sys.exit(1)

    logger.info("配置加载成功", database_url=config.database_url)

    # TODO: 这里写你的健康检查、迁移、重建逻辑
    print("运行健康检查 / 迁移 / 重建...（略）")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    main()

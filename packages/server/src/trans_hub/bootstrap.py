# packages/server/src/trans_hub/bootstrap.py
"""
[DI 重构] 应用引导程序和 DI 容器的生命周期管理。

本模块是应用的唯一初始化入口，负责：
1. 加载配置。
2. 创建并装配 DI 容器。
3. 管理核心资源（如数据库连接池）的启动和关闭。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import structlog
from trans_hub.config import TransHubConfig
from trans_hub.containers import ApplicationContainer

# --- 路径设置 ---
SERVER_ROOT_DIR = Path(__file__).resolve().parents[2]
MONOREPO_ROOT = SERVER_ROOT_DIR.parent.parent
logger = structlog.get_logger("trans_hub.bootstrap")


def _load_dotenv_files(env_mode: Literal["prod", "dev", "test"]) -> list[Path]:
    """根据环境模式，确定并加载相应的 .env 文件。"""
    files_to_load: list[Path] = []
    base_env = SERVER_ROOT_DIR / ".env"
    if base_env.is_file():
        files_to_load.append(base_env)

    dev_env = SERVER_ROOT_DIR / ".env.dev"
    if env_mode in ("dev", "test") and dev_env.is_file():
        files_to_load.append(dev_env)

    test_env = SERVER_ROOT_DIR / ".env.test"
    if env_mode == "test" and test_env.is_file():
        files_to_load.append(test_env)

    logger.debug(
        "Dotenv files determined for loading",
        files=[str(p.relative_to(MONOREPO_ROOT)) for p in files_to_load],
    )
    for file_path in files_to_load:
        try:
            with file_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    if (value.startswith("'") and value.endswith("'")) or (
                        value.startswith('"') and value.endswith('"')
                    ):
                        value = value[1:-1]
                    # 只设置尚未在环境中存在的变量，以尊重外部环境变量的更高优先级
                    if key not in os.environ:
                        os.environ[key] = value
        except Exception as e:
            logger.warning(
                "Failed to parse .env file", path=str(file_path), error=str(e)
            )
    return files_to_load


def create_app_config(env_mode: Literal["prod", "dev", "test"]) -> TransHubConfig:
    """加载、验证并返回应用配置对象。"""
    _load_dotenv_files(env_mode)
    return TransHubConfig()


def create_container(config: TransHubConfig, service_name: str) -> ApplicationContainer:
    """创建并装配 DI 容器。"""
    container = ApplicationContainer()

    # 1. 注入整块配置对象 (pydantic_config)，作为向下传递的唯一事实来源
    container.pydantic_config.override(config)

    # 2. 从整块配置中派生出字段级配置
    container.config.from_pydantic(config)
    container.config.service_name.from_value(service_name)

    # 3. 初始化核心服务（如日志）
    container.core.init_resources()

    return container

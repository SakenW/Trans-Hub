# packages/server/src/trans_hub/bootstrap/init.py
"""
应用引导程序。

本模块是应用的初始化和依赖注入 (DI) 中心，负责加载配置、
创建核心服务实例（如 UoW 工厂、应用服务）并组装它们。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import structlog
from trans_hub.config import TransHubConfig

# [新增] 导入 DI 容器
from trans_hub.di.container import AppContainer
from trans_hub.management.config_utils import mask_db_url

# [关键修复] parents[3] 才指向 packages/server 目录
SERVER_ROOT_DIR = Path(__file__).resolve().parents[3]
MONOREPO_ROOT = SERVER_ROOT_DIR.parent.parent
logger = structlog.get_logger("trans_hub.bootstrap")


# --- .env 加载逻辑 ---
def _load_dotenv_files(env_mode: Literal["prod", "dev", "test"]) -> list[Path]:
    """加载统一的 .env 文件。"""
    files_to_load: list[Path] = []
    base_env = SERVER_ROOT_DIR / ".env"
    if base_env.is_file():
        files_to_load.append(base_env)

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
                    os.environ[key] = value
        except Exception as e:
            logger.warning(
                "Failed to parse .env file", path=str(file_path), error=str(e)
            )
    return files_to_load


def _ensure_no_legacy_prefix() -> None:
    """确保没有使用旧的 TH_ 环境变量前缀。"""
    legacy = [k for k in os.environ.keys() if k.startswith("TH_")]
    if legacy:
        raise RuntimeError(f"检测到遗留环境变量前缀 TH_：{legacy}...")


# --- 核心工厂函数 ---


def create_app_config(env_mode: Literal["prod", "dev", "test"]) -> TransHubConfig:
    """加载、验证并返回应用配置对象。"""
    _ensure_no_legacy_prefix()
    _load_dotenv_files(env_mode)
    
    try:
        config = TransHubConfig(app_env=env_mode)
        logger.debug(
            "Config instance created",
            env_mode=env_mode,
            # [修改] 使用新的工具函数进行安全打印
            final_db_url=mask_db_url(config.database.url),
            final_maint_url=mask_db_url(config.maintenance_database_url)
            if config.maintenance_database_url
            else None,
        )
        return config
    except Exception as e:
        logger.error(
            "Failed to create config",
            env_mode=env_mode,
            error=str(e),
            error_type=type(e).__name__
        )
        raise


# [删除] 所有旧的 create_* 工厂函数
# def create_uow_factory(config: TransHubConfig) -> tuple[UowFactory, Any]: ...
# async def create_coordinator(config: TransHubConfig) -> tuple[Coordinator, Any]: ...


from sqlalchemy.ext.asyncio import AsyncEngine
from trans_hub.management.config_utils import validate_database_connection as _validate_db_connection


def validate_database_connection(config: TransHubConfig) -> bool:
    """验证数据库连接是否可用。"""
    return _validate_db_connection(
        database_url=config.database.url,
        maintenance_url=config.maintenance_database_url,
        connection_type="应用"
    )


def load_config_with_validation(env_mode: Literal["prod", "dev", "test"]) -> TransHubConfig:
    """统一的配置加载入口，包含数据库连接验证。"""
    config = create_app_config(env_mode)
    
    # 在测试环境中验证数据库连接
    if env_mode == "test":
        if not validate_database_connection(config):
            raise RuntimeError(
                f"数据库连接验证失败。请检查：\n"
                f"1. 数据库服务器是否运行在 {config.database.url.host}:{config.database.url.port}\n"
                f"2. 用户 '{config.database.url.username}' 的密码和权限是否正确\n"
                f"3. 数据库 '{config.database.url.database}' 是否存在\n"
                f"4. 网络连接是否正常"
            )
    
    return config


def bootstrap_app(
    env_mode: Literal["prod", "dev", "test"],
    db_engine: AsyncEngine | None = None,
) -> AppContainer:
    """
    应用引导程序：加载配置、初始化并装配 DI 容器。
    这是所有应用入口的统一启动点。
    """
    config = load_config_with_validation(env_mode=env_mode)

    container = AppContainer()
    container.config.override(config)

    # 如果测试环境提供了专用的数据库引擎，则直接覆盖
    if db_engine:
        container.db_engine.override(db_engine)

    container.wire(
        modules=[
            __name__,
            "trans_hub.adapters.cli.main",
            "trans_hub.adapters.cli.commands.db",
            "trans_hub.adapters.cli.commands.request",
            "trans_hub.adapters.cli.commands.status",
            "trans_hub.adapters.cli.commands.worker",
        ]
    )

    return container

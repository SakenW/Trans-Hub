# packages/server/src/trans_hub/bootstrap.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import structlog
from trans_hub.config import TransHubConfig

# 路径计算 (保持不变)
SERVER_ROOT_DIR = Path(__file__).resolve().parents[2]
MONOREPO_ROOT = SERVER_ROOT_DIR.parent.parent


def _load_dotenv_files(env_mode: Literal["prod", "dev", "test"]) -> list[Path]:
    """
    [最终修复] 根据环境模式，安全地加载 .env 文件内容到环境变量中，并确保正确的覆盖优先级。
    """
    files_to_load: list[Path] = []
    
    # 确定加载顺序 (后面的会覆盖前面的)
    base_env = SERVER_ROOT_DIR / ".env"
    if base_env.is_file(): files_to_load.append(base_env)
    dev_env = SERVER_ROOT_DIR / ".env.dev"
    if env_mode in ("dev", "test") and dev_env.is_file(): files_to_load.append(dev_env)
    test_env = SERVER_ROOT_DIR / ".env.test"
    if env_mode == "test" and test_env.is_file(): files_to_load.append(test_env)

    logger = structlog.get_logger("trans_hub.bootstrap.dotenv")
    logger.debug("Dotenv files determined for loading", files=[str(p.relative_to(MONOREPO_ROOT)) for p in files_to_load])
    
    # 1. 将所有 .env 文件的值读入一个临时字典，后面的文件会覆盖前面的。
    dotenv_values: dict[str, str] = {}
    for file_path in files_to_load:
        try:
            with file_path.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, value = line.split('=', 1)
                    key = key.strip()
                    # 简单处理可能存在的引号
                    if (value.startswith("'") and value.endswith("'")) or \
                       (value.startswith('"') and value.endswith('"')):
                        value = value[1:-1]
                    dotenv_values[key] = value
        except Exception as e:
            logger.warning("Failed to parse .env file", path=str(file_path), error=str(e))
            
    # 2. 将临时字典中的值写入 os.environ，但前提是该 key 不存在于原始的环境变量中。
    for key, value in dotenv_values.items():
        # os.environ.setdefault(key, value) 是实现此逻辑的最 Pythonic 的方式
        os.environ.setdefault(key, value)

    return files_to_load


def _ensure_no_legacy_prefix() -> None:
    # ... (此函数保持不变)
    pass


def create_app_config(env_mode: Literal["prod", "dev", "test"]) -> TransHubConfig:
    """
    [最终版] 手动加载 .env 文件到环境变量，然后让 Pydantic 只从环境变量读取。
    这是最健壮、最可预测的配置加载方式。
    """
    _ensure_no_legacy_prefix()
    
    files_loaded = _load_dotenv_files(env_mode)
    
    # 现在，Pydantic 将只从环境变量和默认值中构建配置
    config = TransHubConfig()

    logger = structlog.get_logger("trans_hub.bootstrap.final")
    logger.debug(
        "Config instance created (manual dotenv)",
        env_mode=env_mode,
        files_manually_loaded=[str(p.relative_to(MONOREPO_ROOT)) for p in files_loaded],
        final_db_url=config.database.url,
        final_maint_url=config.maintenance_database_url,
    )
    return config
# packages/server/src/trans_hub/bootstrap.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Literal
import structlog
from trans_hub.config import TransHubConfig

SERVER_ROOT_DIR = Path(__file__).resolve().parents[2]
MONOREPO_ROOT = SERVER_ROOT_DIR.parent.parent

def _load_dotenv_files(env_mode: Literal["prod", "dev", "test"]) -> list[Path]:
    files_to_load: list[Path] = []
    base_env = SERVER_ROOT_DIR / ".env"
    if base_env.is_file(): files_to_load.append(base_env)
    dev_env = SERVER_ROOT_DIR / ".env.dev"
    if env_mode in ("dev", "test") and dev_env.is_file(): files_to_load.append(dev_env)
    test_env = SERVER_ROOT_DIR / ".env.test"
    if env_mode == "test" and test_env.is_file(): files_to_load.append(test_env)

    logger = structlog.get_logger("trans_hub.bootstrap.dotenv")
    logger.debug("Dotenv files determined for loading", files=[str(p.relative_to(MONOREPO_ROOT)) for p in files_to_load])
    
    for file_path in files_to_load:
        try:
            with file_path.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, value = line.split('=', 1)
                    key = key.strip()
                    if (value.startswith("'") and value.endswith("'")) or \
                       (value.startswith('"') and value.endswith('"')):
                        value = value[1:-1]
                    os.environ[key] = value # <-- 关键修复：直接赋值
        except Exception as e:
            logger.warning("Failed to parse .env file", path=str(file_path), error=str(e))
    
    return files_to_load

def _ensure_no_legacy_prefix() -> None:
    legacy = [k for k in os.environ.keys() if k.startswith("TH_")]
    if legacy:
        raise RuntimeError(f"检测到遗留环境变量前缀 TH_：{legacy}...")

def create_app_config(env_mode: Literal["prod", "dev", "test"]) -> TransHubConfig:
    _ensure_no_legacy_prefix()
    files_loaded = _load_dotenv_files(env_mode)
    config = TransHubConfig()
    logger = structlog.get_logger("trans_hub.bootstrap.final")
    logger.debug(
        "Config instance created", env_mode=env_mode,
        files_manually_loaded=[str(p.relative_to(MONOREPO_ROOT)) for p in files_loaded],
        final_db_url=config.database.url,
        final_maint_url=config.maintenance_database_url,
    )
    return config
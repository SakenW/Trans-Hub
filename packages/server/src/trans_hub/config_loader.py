# packages/server/src/trans_hub/config_loader.py
"""
配置装载器（遵守技术宪章）

职责：
- 加载 .env / .env.test；
- 构造 TransHubConfig；
- 严格模式下校验 DSN 驱动（兼容 cfg.database_url 属性别名）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy.engine.url import make_url

from .config import TransHubConfig


def _resolve_env_file(
    mode: str | None = None, dotenv_path: Optional[Path] = None
) -> Optional[Path]:
    """解析 .env 路径：优先显式参数；其后 .env.test（测试）与 .env（默认）。"""
    if dotenv_path:
        p = Path(dotenv_path)
        return p if p.exists() else None
    server_dir = Path(__file__).resolve().parents[3]
    if mode == "test" and (server_dir / ".env.test").exists():
        return server_dir / ".env.test"
    if (server_dir / ".env").exists():
        return server_dir / ".env"
    return None


def load_config_from_env(
    mode: str = "prod", strict: bool = False, dotenv_path: Optional[Path] = None
) -> TransHubConfig:
    """加载环境并返回配置实例。"""
    env_file = _resolve_env_file(mode, dotenv_path)
    if env_file:
        load_dotenv(env_file, override=False)

    cfg = TransHubConfig()

    if strict:
        # 通过属性别名读取扁平字段
        url = make_url(cfg.database_url)
        if not (
            url.drivername.startswith("postgresql+")
            or url.drivername.startswith("sqlite+")
        ):
            raise ValueError(f"不支持的数据库驱动: {url.drivername}")

    return cfg

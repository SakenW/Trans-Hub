# packages/server/src/trans_hub/config_loader.py
# pyright: reportMissingImports=false, reportUnusedImport=false
"""
配置装载器（遵守技术宪章）

职责：
- 加载 .env / .env.test；
- 构造 TransHubConfig；
- 严格模式下校验 DSN 驱动并拒绝任何 TH_* 遗留键。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from dotenv import load_dotenv

# 仅作类型标注与统一入口，TransHubConfig 内部已固定：
# env_prefix="TRANSHUB_", env_nested_delimiter="__"
from trans_hub.config import TransHubConfig


__all__ = ["load_config_from_env"]


# ---------------------------
# 内部工具
# ---------------------------

def _load_env_files(mode: Literal["test", "prod"]) -> None:
    """
    加载 .env / .env.test：
    - test 模式：先加载 .env（override=False），再加载 .env.test（override=True）
    - prod 模式：仅加载 .env（override=False）
    """
    cwd = Path.cwd()
    env_path = cwd / ".env"

    if env_path.exists():
        load_dotenv(env_path, override=False)

    if mode == "test":
        env_test_path = cwd / ".env.test"
        if env_test_path.exists():
            # 测试环境允许 .env.test 覆盖 .env
            load_dotenv(env_test_path, override=True)


def _ensure_no_legacy_prefix(strict: bool) -> None:
    """
    检测遗留前缀（TH_*）。严格模式下直接报错；非严格模式忽略。
    技术宪章规定：权威前缀为 TRANSHUB_，嵌套以 "__" 表示层级。
    """
    if not strict:
        return
    legacy = [k for k in os.environ.keys() if k.startswith("TH_")]
    if legacy:
        raise RuntimeError(
            "检测到遗留环境变量前缀 TH_："
            f"{legacy}。请全部改为 TRANSHUB_ 前缀，并使用双下划线 '__' 表示嵌套，"
            "例如 TRANSHUB_DATABASE__URL。"
        )


def _validate_dsn_drivers(cfg: TransHubConfig, strict: bool) -> None:
    """
    校验 DSN 驱动是否符合“运行期异步 / 运维期同步”的技术宪章。
    - 运行期主库：仅允许
        * sqlite+aiosqlite
        * postgresql+asyncpg
        * mysql+aiomysql
    - 维护库（可选）：若提供，仅允许
        * postgresql+psycopg
      （MySQL / SQLite 通常无需维护库 DSN；留空即可）
    """
    # 主库（嵌套字段为唯一来源）
    db_url = cfg.database.url

    if not db_url:
        raise RuntimeError("未配置数据库 URL。请设置 TRANSHUB_DATABASE__URL。")

    scheme = urlparse(str(db_url)).scheme.lower()

    allowed_async = {
        "sqlite+aiosqlite",
        "postgresql+asyncpg",
        "mysql+aiomysql",
    }

    if scheme not in allowed_async:
        msg = (
            f"不支持的运行期数据库驱动：{scheme!r}。"
            "仅允许 sqlite+aiosqlite / postgresql+asyncpg / mysql+aiomysql。"
        )
        if strict:
            raise RuntimeError(msg)

    # 维护库（可选，主要用于 Alembic/工具）
    maint_url = cfg.maintenance_database_url
    if maint_url:
        maint_scheme = urlparse(str(maint_url)).scheme.lower()
        if maint_scheme != "postgresql+psycopg":
            # 若确有强需求，可在此扩展 MySQL 同步驱动校验，但当前按宪章仅允许 PG 维护库。
            msg = (
                f"维护库 DSN 需为 postgresql+psycopg，实际为：{maint_scheme!r}。"
                "请设置 TRANSHUB_MAINTENANCE_DATABASE_URL，例如："
                "postgresql+psycopg://user:pass@host:5432/postgres。"
            )
            if strict:
                raise RuntimeError(msg)


# ---------------------------
# 公共入口
# ---------------------------

def load_config_from_env(
    mode: Literal["test", "prod"] = "test",
    strict: bool = True,
) -> TransHubConfig:
    """
    加载并构造配置对象；在严格模式下对 DSN 驱动与遗留前缀做约束校验。

    参数：
      - mode: "test" | "prod"；决定是否加载 .env.test 覆盖项
      - strict: True 时启用严格校验（禁止 TH_* 前缀；校验 DSN 驱动）

    返回：
      - TransHubConfig 实例（以 TRANSHUB_ 前缀 + '__' 嵌套从环境加载）
    """
    _load_env_files(mode)
    _ensure_no_legacy_prefix(strict=strict)

    cfg = TransHubConfig()  # 内部固定：env_prefix="TRANSHUB_", env_nested_delimiter="__"
    _validate_dsn_drivers(cfg, strict=strict)

    return cfg

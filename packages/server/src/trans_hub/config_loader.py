# packages/server/src/trans_hub/config_loader.py
"""
统一、简洁的配置加载器。
(v26) 目标：
- 按环境(test/prod)优先加载对应 .env.test / .env（可显式指定路径）
- 测试可设置 strict=True：.env.test 不存在就报错，绝不回退到 .env
- 非测试可宽松：没找到 .env 也可直接走已有环境变量
- 不做任何“脱敏写回”操作；脱敏仅在打印时处理
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Literal, Optional

import structlog
from dotenv import load_dotenv

from .config import TransHubConfig

logger = structlog.get_logger(__name__)

EnvMode = Literal["test", "prod"]


def _server_root() -> Path:
    # 本文件在 packages/server/src/trans_hub/ 下
    # server 根目录：packages/server
    return Path(__file__).resolve().parents[2]


def _resolve_default_env_path(mode: EnvMode) -> Path:
    root = _server_root()
    return root / (".env.test" if mode == "test" else ".env")


def load_config_from_env(
    mode: Optional[EnvMode] = None,
    *,
    strict: bool = False,
    dotenv_path: Optional[os.PathLike[str] | str] = None,
) -> TransHubConfig:
    """
    统一加载入口，返回 TransHubConfig 实例。

    参数:
        mode: "test" 或 "prod"。为 None 时，优先读 TH_ENV=test|production 推断，
              推断不到则默认 "prod"（应用更安全）。——若你真想默认 test，请在调用处传入 mode="test"。
        strict: 严格模式：
            - 对 test: 若找不到 .env.test 且未指定 dotenv_path，直接报错；绝不回退到 .env。
            - 对 prod: 若找不到 .env 且未指定 dotenv_path，报错或走已有环境变量（见下）。
        dotenv_path: 显式指定 .env 路径（优先级最高），常用于 CI。

    行为说明：
        1) 从 dotenv_path 或默认路径加载对应 .env 文件（如存在）。
        2) strict=True 时，要求关键变量存在，否则抛异常；
           strict=False 时，若缺失 .env 但环境变量已齐，可以继续。
        3) 绝不对任何环境变量做“掩码写回”。脱敏仅用于日志打印。
    """
    # 1) 确定 mode
    if mode is None:
        th_env = os.getenv("TH_ENV", "").lower()
        if th_env == "test":
            mode = "test"  # type: ignore[assignment]
        else:
            mode = "prod"  # 默认生产更安全

    # 2) 预置 TH_ENV 方便上层做分支控制（如生产保护）
    os.environ.setdefault("TH_ENV", "test" if mode == "test" else "production")

    # 3) 决定 .env 文件路径
    env_file = Path(dotenv_path) if dotenv_path else _resolve_default_env_path(mode)

    # 4) 加载 .env（若存在）
    if env_file.is_file():
        logger.info("加载 .env 文件", path=str(env_file))
        load_dotenv(dotenv_path=env_file, override=True)
    else:
        # test 模式严格禁止回退到 .env
        if mode == "test":
            if strict:
                raise FileNotFoundError(
                    f"严格模式：未找到测试环境变量文件：{env_file}。请提供 .env.test 或使用 dotenv_path 指定。"
                )
            else:
                logger.warning(
                    "未找到测试环境变量文件，将直接使用当前环境变量（不会回退到 .env）。",
                    expected=str(env_file),
                )
        else:
            # prod 模式可以更宽松：若没有 .env，允许使用已有环境变量
            if strict:
                raise FileNotFoundError(
                    f"严格模式：未找到正式环境变量文件：{env_file}。"
                )
            else:
                logger.warning(
                    "未找到正式环境变量文件，将直接使用当前环境变量。",
                    expected=str(env_file),
                )

    # 5) 实例化配置
    cfg = TransHubConfig()

    # 6) 严格校验关键变量
    def _has(v: Optional[str]) -> bool:
        return bool(v and v.strip())

    if not _has(cfg.database_url):
        raise ValueError("缺少 TH_DATABASE_URL。请在对应 .env 或环境变量中提供。")

    # 维护库 URL 可选，但很多管理操作需要；给出提示
    if not _has(cfg.maintenance_database_url):
        logger.warning(
            "TH_MAINTENANCE_DATABASE_URL 未设置。某些管理功能（如建库/删库）可能不可用。"
        )

    return cfg

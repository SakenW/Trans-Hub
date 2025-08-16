# packages/server/src/trans_hub/bootstrap.py
"""
应用引导程序 (Bootstrap)

本模块是整个 Trans-Hub 应用配置加载的单一事实来源 (SSOT)。
它提供了一个核心工厂函数 `create_app_config`，用于根据指定的环境模式
(如 "prod", "test") 可靠地构造并返回 `TransHubConfig` 实例。

职责:
- 根据环境模式，确定要加载的 .env 文件列表及其优先级。
- 利用 pydantic-settings 的强大功能，以正确的顺序加载配置。
- 执行在配置加载后必须进行的、符合技术宪章的严格校验。
- 成为 CLI、测试、Alembic 和应用运行时获取配置的唯一入口。
"""
from __future__ import annotations

import os
from typing import Literal

from pydantic_settings import SettingsConfigDict
from trans_hub.config import TransHubConfig


def _ensure_no_legacy_prefix() -> None:
    """
    检测并禁止遗留的 TH_* 环境变量前缀，强制遵守宪章。
    """
    legacy = [k for k in os.environ.keys() if k.startswith("TH_")]
    if legacy:
        raise RuntimeError(
            f"检测到遗留环境变量前缀 TH_：{legacy}。"
            "请全部改为 TRANSHUB_ 前缀，并使用双下划线 '__' 表示嵌套。"
        )


def create_app_config(env_mode: Literal["prod", "test"]) -> TransHubConfig:
    """
    根据环境模式创建、校验并返回应用配置。

    这是获取配置的唯一入口点。

    Args:
        env_mode:
            - "prod": 加载 `.env` (如果存在)。用于生产、CLI 和示例。
            - "test": 依次加载 `.env` 和 `.env.test`，后者会覆盖前者。
                      用于自动化测试。

    Returns:
        经过验证的 TransHubConfig 实例。
    """
    _ensure_no_legacy_prefix()

    env_files = [".env"]
    if env_mode == "test":
        env_files.append(".env.test")

    # 动态创建 Pydantic Settings 配置字典
    # pydantic-settings 会从左到右加载文件，后面的文件会覆盖前面的。
    settings_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_prefix="TRANSHUB_",
        case_sensitive=False,
        extra="ignore",
        env_file=tuple(env_files),  # 必须是元组
        env_file_encoding="utf-8",
    )

    # 使用动态配置来实例化 TransHubConfig
    config = TransHubConfig(_settings=settings_config)

    # 在这里可以添加更多的后加载校验逻辑
    # 例如，确保测试数据库的名称符合特定模式等。

    return config
# packages/server/src/trans_hub/config_loader.py
"""
统一、简洁的配置加载器（改良版）
- prod 模式使用 `.env`，test 模式使用 `.env.test`（生态友好）
- 自顶向上查找项目根（含 packages + pyproject.toml）
- 回退路径与主路径一致：都在 <project_root>/packages/server 下查找
- strict=True 时强校验 .env 与关键变量
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional, Union, Any

import structlog
from dotenv import load_dotenv

from .config import TransHubConfig

logger = structlog.get_logger(__name__)

PathLike = Union[os.PathLike[str], str]


def find_project_root(start_dir: Path) -> Path:
    """
    从起始目录向上查找包含 'packages' 目录且带有 'pyproject.toml' 的项目根。
    约定：monorepo 根目录结构应包含:
      - packages/
      - pyproject.toml
    """
    current = start_dir.resolve()
    while current.parent != current:
        if (current / "packages").is_dir() and (current / "pyproject.toml").is_file():
            return current
        current = current.parent
    raise FileNotFoundError(f"无法从 '{start_dir}' 向上找到项目根目录。")


def _resolve_env_file(
    mode: Literal["test", "prod"],
    *,
    dotenv_path: Optional[PathLike] = None,
) -> Path:
    """
    计算应加载的 .env 文件路径。
    优先级：
      1) 显式传入的 dotenv_path
      2) <project_root>/packages/server/{.env | .env.test}
      3) 回退：<cwd>/packages/server/{.env | .env.test}
    """
    # 1) 显式路径优先
    if dotenv_path:
        return Path(dotenv_path)

    # 根据模式确定文件名：prod→.env，test→.env.test
    env_filename = ".env" if mode == "prod" else ".env.test"

    # 2) 以源码文件所在目录为锚点自顶向上找项目根
    try:
        project_root = find_project_root(Path(__file__).parent)
        return project_root / "packages" / "server" / env_filename
    except FileNotFoundError:
        # 3) 回退到 CWD，但仍保持 packages/server 的路径结构一致
        project_root = Path.cwd()
        return project_root / "packages" / "server" / env_filename


def load_config_from_env(
    mode: Literal["test", "prod"] = "prod",
    *,
    strict: bool = False,
    dotenv_path: Optional[PathLike] = None,
) -> TransHubConfig:
    """
    从 .env 文件或环境变量加载配置。

    Args:
        mode: "test" 或 "prod"。prod 使用 `.env`；test 使用 `.env.test`。
        strict: 严格模式。若为 True：
                - 未找到目标 .env 文件将抛出 FileNotFoundError
                - 缺少关键环境变量将抛出 ValueError
        dotenv_path: 显式指定 .env 文件路径，优先级最高。
    """
    env_file = _resolve_env_file(mode, dotenv_path=dotenv_path)

    if env_file.is_file():
        logger.info("加载 .env 文件", path=str(env_file))
        # override=True：.env 覆盖进程已有的环境变量，保证本地开发一致性
        load_dotenv(dotenv_path=env_file, override=True)
    else:
        if strict:
            raise FileNotFoundError(f"严格模式下未找到所需的 .env 文件: {env_file}")
        # 注意：这里不使用 f-string，占位信息放在结构化字段里
        logger.warning(".env 文件未找到，将仅使用环境变量", expected_path=str(env_file))

    if strict:
        # 关键变量校验：根据你的项目约定增减
        required_vars = ["TH_DATABASE_URL", "TH_MAINTENANCE_DATABASE_URL"]
        missing_vars = [v for v in required_vars if not os.getenv(v)]
        if missing_vars:
            raise ValueError(f"严格模式下缺少必要的环境变量: {', '.join(missing_vars)}")

    # 由 Pydantic Settings 类负责进一步解析与校验
    return TransHubConfig()

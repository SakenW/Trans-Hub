# trans_hub/config.py
"""本模块使用 Pydantic 定义了 Trans-Hub 项目的主配置模型和相关的子模型。"""

import enum
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.cache import CacheConfig


class EngineName(str, enum.Enum):
    DEBUG = "debug"
    OPENAI = "openai"
    TRANSLATORS = "translators"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: Literal["json", "console"] = "console"


class RetryPolicyConfig(BaseModel):
    """重试策略配置。"""

    # 修复：为所有数值型参数添加正数校验
    max_attempts: int = Field(default=2, gt=0)
    initial_backoff: float = Field(default=1.0, gt=0)
    max_backoff: float = Field(default=60.0, gt=0)


class TransHubConfig(BaseSettings):
    """Trans-Hub 的主配置对象，聚合了所有子配置。"""

    model_config = SettingsConfigDict(
        env_prefix="TH_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite:///transhub.db"
    active_engine: EngineName = EngineName.TRANSLATORS
    batch_size: int = Field(default=50, gt=0)
    source_lang: str | None = Field(default=None)
    gc_retention_days: int = Field(default=90, gt=0)
    worker_poll_interval: int = Field(
        default=10, description="Worker在轮询模式下的等待间隔（秒）", gt=0
    )

    cache_config: CacheConfig = Field(default_factory=CacheConfig)
    engine_configs: dict[str, Any] = Field(default_factory=dict)
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @property
    def db_path(self) -> str:
        parsed_url = urlparse(self.database_url)
        if parsed_url.scheme != "sqlite":
            raise ValueError("db_path 属性仅在 database_url 为 'sqlite' 时可用。")
        path = parsed_url.netloc + parsed_url.path
        if path.startswith("/") and ":" not in path:
            return path[1:]
        return path

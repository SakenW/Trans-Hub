# trans_hub/config.py

import enum
import os
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.cache import CacheConfig
from trans_hub.utils import validate_lang_codes


class EngineName(str, enum.Enum):
    DEBUG = "debug"
    OPENAI = "openai"
    TRANSLATORS = "translators"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: Literal["json", "console"] = "console"


class RetryPolicyConfig(BaseModel):
    max_attempts: int = Field(default=2, gt=0)
    initial_backoff: float = Field(default=1.0, gt=0)
    max_backoff: float = Field(default=60.0, gt=0)

    @model_validator(mode="after")
    def check_backoff_consistency(self) -> "RetryPolicyConfig":
        if self.max_backoff < self.initial_backoff:
            raise ValueError("max_backoff 必须大于或等于 initial_backoff")
        return self


class TransHubConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TH_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite+aiosqlite:///transhub.db"
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

    @field_validator("source_lang")
    @classmethod
    def validate_source_lang_code(cls, v: str | None) -> str | None:
        if v is not None:
            validate_lang_codes([v])
        return v

    @property
    def db_path(self) -> str:
        parsed_url = urlparse(self.database_url)
        # --- [核心修复] 检查 scheme 是否以 'sqlite' 开头 ---
        if not parsed_url.scheme.startswith("sqlite"):
            raise ValueError("db_path 属性仅在 database_url 为 sqlite 类型时可用。")

        # 从 URL 中提取路径部分 (例如, '///path/to/db.sqlite' -> '/path/to/db.sqlite')
        path = parsed_url.path

        # 移除 Windows 驱动器号前的斜杠 (例如, '/C:/...' -> 'C:/...')
        if (
            os.name == "nt"
            and path.startswith("/")
            and len(path) > 2
            and path[2] == ":"
        ):
            path = path[1:]

        # 移除 Unix/macOS 绝对路径前的多余斜杠
        while path.startswith("//"):
            path = path[1:]

        return path

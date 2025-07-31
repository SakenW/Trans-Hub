# trans_hub/config.py
"""本模块使用 Pydantic 定义了 Trans-Hub 项目的主配置模型和相关的子模型。"""

import enum
from typing import Any, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.cache import CacheConfig
from trans_hub.engines.debug import DebugEngineConfig
from trans_hub.engines.openai import OpenAIEngineConfig
from trans_hub.engines.translators_engine import TranslatorsEngineConfig


class EngineName(str, enum.Enum):
    DEBUG = "debug"
    OPENAI = "openai"
    TRANSLATORS = "translators"
    MOCK_ENGINE = "mock_engine"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: Literal["json", "console"] = "console"


class RetryPolicyConfig(BaseModel):
    max_attempts: int = 2
    initial_backoff: float = 1.0
    max_backoff: float = 60.0


class EngineConfigs(BaseModel):
    debug: Optional[DebugEngineConfig] = None
    openai: Optional[OpenAIEngineConfig] = None
    translators: Optional[TranslatorsEngineConfig] = None
    mock_engine: Optional[Any] = None
    model_config = ConfigDict(extra="allow")


class TransHubConfig(BaseSettings):
    """Trans-Hub 的主配置对象，聚合了所有子配置。"""

    model_config = SettingsConfigDict(
        env_prefix="TH_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite:///transhub.db"
    active_engine: EngineName = EngineName.TRANSLATORS
    batch_size: int = Field(default=50)
    source_lang: Optional[str] = Field(default=None)
    gc_retention_days: int = Field(default=90)
    cache_config: CacheConfig = Field(default_factory=CacheConfig)
    engine_configs: EngineConfigs = Field(default_factory=EngineConfigs)
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @property
    def db_path(self) -> str:
        parsed_url = urlparse(self.database_url)
        if parsed_url.scheme != "sqlite":
            raise ValueError("目前只支持 'sqlite' 数据库 URL。")
        path = parsed_url.netloc or parsed_url.path
        # 对于相对路径 (sqlite:///transhub.db)，去掉开头的斜杠
        if path.startswith("/") and ":" not in path:
            return path[1:]
        # 对于绝对路径 (sqlite:////absolute/path.db 或 sqlite://localhost/path.db)
        return path

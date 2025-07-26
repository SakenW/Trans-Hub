# trans_hub/config.py
"""
定义了 Trans-Hub 项目的主配置模型和相关的子模型。
此版本将所有动态配置逻辑移交给了 Coordinator，
使得配置模型本身保持简单、静态和无循环依赖。
"""

from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from trans_hub.cache import CacheConfig


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: Literal["json", "console"] = "console"


class RetryPolicyConfig(BaseModel):
    max_attempts: int = 2
    initial_backoff: float = 1.0
    max_backoff: float = 60.0


class EngineConfigs(BaseModel):
    """
    一个用于聚合所有引擎特定配置的基础模型。
    它是一个简单的容器，由 Coordinator 在运行时填充和验证。
    """

    model_config = ConfigDict(extra="allow")


class TransHubConfig(BaseModel):
    """Trans-Hub 的主配置对象。"""

    database_url: str = "sqlite:///transhub.db"
    active_engine: str = "translators"
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
        if path.startswith("/") and ":" in path:
            return path[1:]
        return path

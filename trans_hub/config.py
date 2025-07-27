# trans_hub/config.py
"""本模块使用 Pydantic 定义了 Trans-Hub 项目的主配置模型和相关的子模型。"""

import enum
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings

from trans_hub.cache import CacheConfig
from trans_hub.exceptions import ConfigurationError


class EngineName(str, enum.Enum):
    """定义了所有受支持的翻译引擎的名称。"""

    DEBUG = "debug"
    OPENAI = "openai"
    TRANSLATORS = "translators"


class LoggingConfig(BaseModel):
    """日志配置。"""

    level: str = "INFO"
    format: Literal["json", "console"] = "console"


class RetryPolicyConfig(BaseModel):
    """重试策略配置。"""

    max_attempts: int = 2
    initial_backoff: float = 1.0
    max_backoff: float = 60.0


class EngineConfigs(BaseModel):
    """一个用于聚合所有引擎特定配置的容器模型。"""

    model_config = ConfigDict(extra="allow")


class TransHubConfig(BaseSettings):
    """Trans-Hub 的主配置对象，聚合了所有子配置。"""

    # --- 核心修正：添加 extra='ignore' ---
    # 告诉 Pydantic 忽略它在 .env 文件中不认识的字段（如 TH_OPENAI_*)
    model_config = {
        "env_prefix": "TH_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    database_url: str = "sqlite:///transhub.db"
    active_engine: EngineName = EngineName.TRANSLATORS
    batch_size: int = Field(default=50)
    source_lang: Optional[str] = Field(default=None)
    gc_retention_days: int = Field(default=90)

    engine_configs: EngineConfigs = Field(default_factory=EngineConfigs)
    cache_config: CacheConfig = Field(default_factory=CacheConfig)
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @model_validator(mode="after")
    def check_active_engine_config_exists(self) -> "TransHubConfig":
        """在配置加载后，立即验证活动引擎的配置是否存在。"""
        engine_name_str = self.active_engine.value
        if not hasattr(self.engine_configs, engine_name_str):
            raise ConfigurationError(
                f"活动引擎 '{engine_name_str}' 已指定, 但其配置块 "
                f"不存在于 'engine_configs' 中。"
            )
        return self

    @property
    def db_path(self) -> str:
        """从 database_url 中解析出 SQLite 数据库文件的路径。"""
        parsed_url = urlparse(self.database_url)
        if parsed_url.scheme != "sqlite":
            raise ValueError("目前只支持 'sqlite' 数据库 URL。")
        path = parsed_url.netloc or parsed_url.path
        if path.startswith("/") and ":" in path:
            return path[1:]
        return path

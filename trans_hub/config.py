# trans_hub/config.py
"""本模块使用 Pydantic 定义了 Trans-Hub 项目的主配置模型和相关的子模型。"""

import enum
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings

# 导入 CacheConfig 及其依赖的模块
from trans_hub.cache import CacheConfig

# 导入所有引擎配置模型，以便在 EngineConfigs 中引用
from trans_hub.engines.debug import DebugEngineConfig
from trans_hub.engines.openai import OpenAIEngineConfig
from trans_hub.engines.translators_engine import TranslatorsEngineConfig
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

    # 核心修正：明确定义字段，mypy 才能识别
    debug: Optional[DebugEngineConfig] = None
    openai: Optional[OpenAIEngineConfig] = None
    translators: Optional[TranslatorsEngineConfig] = None

    # 仍然保留 extra="allow" 以备未来动态添加更多引擎
    model_config = ConfigDict(extra="allow")


class TransHubConfig(BaseSettings):
    """Trans-Hub 的主配置对象，聚合了所有子配置。"""

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
    cache_config: CacheConfig = Field(default_factory=CacheConfig)
    engine_configs: EngineConfigs = Field(default_factory=EngineConfigs)
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @model_validator(mode="after")
    def check_active_engine_config_exists(self) -> "TransHubConfig":
        engine_name_str = self.active_engine.value
        if not hasattr(self.engine_configs, engine_name_str):
            raise ConfigurationError(
                f"活动引擎 '{engine_name_str}' 已指定, 但其配置块 不存在于 'engine_configs' 中。"
            )
        return self

    @property
    def db_path(self) -> str:
        parsed_url = urlparse(self.database_url)
        if parsed_url.scheme != "sqlite":
            raise ValueError("目前只支持 'sqlite' 数据库 URL。")
        path = parsed_url.netloc or parsed_url.path
        if path.startswith("/") and ":" in path:
            return path[1:]
        return path

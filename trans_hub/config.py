# trans_hub/config.py
"""
本模块使用 Pydantic 定义了 Trans-Hub 项目的主配置模型和相关的子模型。

它作为配置的静态“蓝图”，具体的填充和动态验证逻辑由 Coordinator 负责。
"""

from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from trans_hub.cache import CacheConfig


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
    """
    一个用于聚合所有引擎特定配置的容器模型。

    它是一个简单的动态容器，由 Coordinator 在运行时填充和验证。
    """

    model_config = ConfigDict(extra="allow")


class TransHubConfig(BaseModel):
    """Trans-Hub 的主配置对象，聚合了所有子配置。"""

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
        """从 database_url 中解析出 SQLite 数据库文件的路径。"""
        parsed_url = urlparse(self.database_url)
        if parsed_url.scheme != "sqlite":
            raise ValueError("目前只支持 'sqlite' 数据库 URL。")
        path = parsed_url.netloc or parsed_url.path
        if path.startswith("/") and ":" in path:  # 处理 Windows 绝对路径
            return path[1:]
        return path

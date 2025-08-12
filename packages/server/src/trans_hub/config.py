# packages/server/src/trans_hub/config.py
"""
定义 Trans-Hub Server 的所有配置选项。
"""
from typing import Any, Literal, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from langcodes import tag_is_valid

class LoggingConfig(BaseSettings):
    """日志配置。"""
    model_config = SettingsConfigDict(env_prefix="TH_LOGGING_")
    level: str = "INFO"
    format: Literal["json", "console"] = "console"


class WorkerConfig(BaseSettings):
    """后台 Worker 配置。"""
    model_config = SettingsConfigDict(env_prefix="TH_WORKER_")
    batch_size: int = Field(50, gt=0, description="单次从数据库获取任务进行处理的最大批次大小。")
    poll_interval: int = Field(10, gt=0, description="在轮询模式下，Worker 两次检查之间的等待间隔（秒）。")
    event_stream_name: str = Field("trans_hub::events", description="用于发布系统事件的 Redis Stream 名称。")
    translation_queue_name: str = Field("trans_hub::queue::translations", description="用于后台翻译任务的队列名称。")

class CacheConfig(BaseSettings):
    """缓存配置"""
    model_config = SettingsConfigDict(env_prefix="TH_CACHE_CONFIG__")
    ttl: int = Field(3600, description="缓存默认 TTL（秒）")
    maxsize: int = Field(1000, description="缓存最大条目数（LRU 模式下生效）")

class RetryPolicyConfig(BaseSettings):
    """重试策略配置"""
    model_config = SettingsConfigDict(env_prefix="TH_RETRY_POLICY__")
    max_attempts: int = 2
    initial_backoff: float = 1.0
    max_backoff: float = 60.0

class TransHubConfig(BaseSettings):
    """
    主配置类，从环境变量和 .env 文件中加载。
    """
    model_config = SettingsConfigDict(
        env_prefix="TH_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
    database_url: str = Field(..., description="主应用数据库的 SQLAlchemy 连接 URL。")
    maintenance_database_url: Optional[str] = Field(
        None, 
        description="用于数据库管理的维护连接 URL (例如，指向 'postgres' 数据库)。"
    )
    redis_url: Optional[str] = Field(None, description="Redis 的连接 URL。")
    redis_key_prefix: str = Field("th:dev:", description="缓存 key 前缀（区分环境）")
    
    # --- 业务逻辑配置 ---
    default_source_lang: str = Field("en", description="默认的源语言代码 (例如 'en', 'zh-CN')。")
    default_resolve_ttl_seconds: int = Field(60, gt=0, description="解析缓存的默认 TTL (秒)。")
    active_engine: str = Field("debug", description="默认启用的翻译引擎，可选：debug | translators | openai")
    
    # --- 模块配置 ---
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    cache_config: CacheConfig = Field(default_factory=CacheConfig)
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    
    # --- 引擎动态配置 ---
    engines: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("default_source_lang")
    @classmethod
    def _validate_lang_code(cls, v: str | None) -> str | None:
        """校验语言代码是否符合 BCP-47 规范。"""
        if v is not None:
            if not tag_is_valid(v):
                raise ValueError(f"'{v}' 不是一个有效的 BCP-47 语言标签。")
        return v
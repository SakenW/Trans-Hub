# packages/server/src/trans_hub/config.py
"""
定义 Trans-Hub Server 的所有配置选项。

本模块使用 pydantic-settings，可以从环境变量或 .env 文件中自动加载配置。
所有配置项都以 `TH_` 作为前缀。
"""
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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


class TransHubConfig(BaseSettings):
    """
    Trans-Hub Server 的主配置模型。
    """
    model_config = SettingsConfigDict(
        env_prefix="TH_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- 核心配置 ---
    database_url: str = Field(
        "sqlite+aiosqlite:///transhub.db",
        description="主数据库的 SQLAlchemy 连接 URL。"
    )
    redis_url: str | None = Field(None, description="Redis 的连接 URL (例如 'redis://localhost:6379/0')。")

    # --- 业务逻辑配置 ---
    default_source_lang: str | None = Field(None, description="默认的源语言代码 (例如 'en', 'zh-CN')。")
    default_resolve_ttl_seconds: int = Field(60, gt=0, description="解析缓存的默认 TTL (秒)。")

    # --- 模块配置 ---
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)

    # --- 引擎动态配置 ---
    # 允许在 .env 中通过 TH_ENGINES__OPENAI__MODEL='gpt-4o' 的形式进行配置
    engines: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("default_source_lang")
    @classmethod
    def _validate_lang_code(cls, v: str | None) -> str | None:
        """校验语言代码是否符合 BCP-47 规范。"""
        if v is not None:
            try:
                from langcodes import Language
                Language.get(v)
            except Exception as e:
                raise ValueError(f"无效的 BCP-47 语言代码: '{v}'") from e
        return v
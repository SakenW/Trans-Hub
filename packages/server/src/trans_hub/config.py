# packages/server/src/trans_hub/config.py
"""
Trans-Hub Server 配置（Pydantic v2，最终简洁版）

特性:
- 恢复使用 `default_factory`，代码更简洁，因为它信赖加载器 (bootstrap.py)
  已经保证了环境的正确性。
- 保持纯粹数据模型的职责。
"""

from __future__ import annotations

from typing import Literal, Optional

import langcodes
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import make_url

# ===================== 子模型 =====================


class DatabaseSettings(BaseModel):
    """主库（运行期异步驱动）"""

    url: str = Field(
        default="sqlite+aiosqlite:///transhub.db",
        description="异步 DSN（sqlite+aiosqlite / postgresql+asyncpg / mysql+aiomysql）",
    )
    echo: bool = Field(default=False, description="SQLAlchemy echo（调试）")

    @field_validator("url")
    @classmethod
    def _validate_async_driver(cls, v: str) -> str:
        allowed = {"sqlite+aiosqlite", "postgresql+asyncpg", "mysql+aiomysql"}
        try:
            drv = make_url(v).drivername.lower()
        except Exception as e:
            raise ValueError(f"非法数据库 URL：{v!r}（{e}）") from e
        if drv not in allowed:
            raise ValueError(
                f"不支持的运行期数据库驱动：{drv!r}，仅允许 {', '.join(allowed)}"
            )
        return v


class RedisClusterSettings(BaseModel):
    nodes: Optional[str] = Field(default=None)


class RedisSentinelSettings(BaseModel):
    nodes: Optional[str] = Field(default=None)
    master: Optional[str] = Field(default=None)


class CacheSettings(BaseModel):
    ttl: int = Field(default=3600, ge=1)
    maxsize: int = Field(default=1000, ge=1)


class RedisSettings(BaseModel):
    url: Optional[str] = Field(default=None)
    key_prefix: str = Field(default="th:dev:")
    cluster: RedisClusterSettings = Field(default_factory=RedisClusterSettings)
    sentinel: RedisSentinelSettings = Field(default_factory=RedisSentinelSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)


class WorkerSettings(BaseModel):
    event_stream_name: str = Field(default="th_events")
    poll_interval: float = Field(default=2.0, gt=0)


class LoggingSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    format: Literal["console", "json"] = Field(default="console")


class RetryPolicySettings(BaseModel):
    max_attempts: int = Field(default=2, ge=0)
    initial_backoff: float = Field(default=1.0, gt=0)
    max_backoff: float = Field(default=60.0, gt=0)


class QueueSettings(BaseModel):
    kind: Literal["redis", "db"] = Field(default="db")
    prefix: str = Field(default="th:queue:")
    streams_prefix: str = Field(default="th:streams:")


class OpenAISettings(BaseModel):
    api_key: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    temperature: float = Field(default=0.1, ge=0)
    timeout: float = Field(default=60.0, gt=0)
    connect_timeout: float = Field(default=5.0, gt=0)
    max_retries: int = Field(default=2, ge=0)


class TranslatorsSettings(BaseModel):
    provider: Optional[str] = Field(default=None)


class DebugEngineSettings(BaseModel):
    mode: Literal["SUCCESS", "FAIL"] = Field(default="SUCCESS")
    fail_on_text: Optional[str] = Field(default=None)
    fail_is_retryable: bool = Field(default=True)


class ObservabilitySettings(BaseModel):
    otel_exporter: Optional[str] = Field(default=None)


# ===================== 顶层配置 =====================
class TransHubConfig(BaseSettings):
    """
    Trans-Hub 核心配置模型。
    """

    # --- 服务器通用 ---
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # --- 领域子配置 (恢复使用 default_factory) ---
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    retry_policy: RetryPolicySettings = Field(default_factory=RetryPolicySettings)
    queue: QueueSettings = Field(default_factory=QueueSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    translators: TranslatorsSettings = Field(default_factory=TranslatorsSettings)
    debug_engine: DebugEngineSettings = Field(default_factory=DebugEngineSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    # --- 连接池高级参数 ---
    db_pool_size: Optional[int] = None
    db_max_overflow: Optional[int] = None
    db_pool_timeout: int = 30
    db_pool_recycle: Optional[int] = None
    db_pool_pre_ping: bool = True
    db_echo: bool = False

    # --- 维护库 ---
    maintenance_database_url: Optional[str] = None

    # --- 语言/引擎/批量/GC ---
    default_source_lang: Optional[str] = None
    active_engine: Literal["debug", "translators", "openai"] = "debug"
    batch_size: int = 50
    gc_retention_days: int = 90

    # --- 校验器 ---
    @field_validator("default_source_lang")
    @classmethod
    def _validate_lang(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if not langcodes.tag_is_valid(v):
            raise ValueError(f"非法语言代码: {v}")
        return v

    @field_validator("maintenance_database_url", mode="before")
    @classmethod
    def _autofill_maint(cls, v: Optional[str], info):
        if v:
            try:
                drv = make_url(v).drivername.lower()
            except Exception as e:
                raise ValueError(f"非法维护库 DSN：{v!r}（{e}）") from e
            if drv != "postgresql+psycopg":
                raise ValueError(
                    f"维护库驱动需为 'postgresql+psycopg'，实际为：{drv!r}"
                )
            return v
        data = getattr(info, "data", {}) or {}
        db = data.get("database")
        dsn = getattr(db, "url", None) if db is not None else None
        if not isinstance(dsn, str):
            return v
        try:
            url = make_url(dsn)
        except Exception:
            return v
        if url.get_backend_name().startswith("postgresql"):
            return str(url.set(drivername="postgresql+psycopg", database="postgres"))
        return v

    # --- Pydantic v2 设置 ---
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_prefix="TRANSHUB_",
        case_sensitive=False,
        extra="ignore",
        env_file_encoding="utf-8",
    )

"""
Trans-Hub Server 配置（Pydantic v2，遵守技术宪章 · 全面优化版）

特性
- 仅做“值与校验”，不产生副作用（不创建引擎/连接/客户端）。
- 统一使用环境变量前缀 TRANSHUB_，并以双下划线 "__" 表示嵌套：
    例：TRANSHUB_DATABASE__URL -> config.database.url
- 内置严格校验：
    * 运行期主库仅允许：sqlite+aiosqlite / postgresql+asyncpg / mysql+aiomysql
    * 维护库（若提供）仅允许：postgresql+psycopg
    * 主库为 Postgres 且未显式维护库时，自动推导 psycopg + postgres
    * 语言码按 BCP-47 校验
- 不再提供任何历史兼容（如 TH_* 前缀、扁平字段别名等）。
"""

from __future__ import annotations

from typing import Literal, Optional

import langcodes
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
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
        # 允许的运行期异步驱动
        allowed = {
            "sqlite+aiosqlite",
            "postgresql+asyncpg",
            "mysql+aiomysql",
        }
        try:
            drv = make_url(v).drivername.lower()
        except Exception as e:
            raise ValueError(f"非法数据库 URL：{v!r}（{e}）")
        if drv not in allowed:
            raise ValueError(
                f"不支持的运行期数据库驱动：{drv!r}，"
                "仅允许 sqlite+aiosqlite / postgresql+asyncpg / mysql+aiomysql"
            )
        return v


class RedisClusterSettings(BaseModel):
    """Redis 集群（预留占位）"""

    nodes: Optional[str] = Field(
        default=None,
        description="逗号分隔节点，如 redis://n1:6379,redis://n2:6379",
    )


class RedisSentinelSettings(BaseModel):
    """Redis Sentinel（预留占位）"""

    nodes: Optional[str] = Field(default=None, description="host:port,host:port")
    master: Optional[str] = Field(default=None, description="主节点名，如 mymaster")


class CacheSettings(BaseModel):
    """缓存策略（可选增强）"""

    ttl: int = Field(default=3600, ge=1, description="默认 TTL（秒）")
    maxsize: int = Field(default=1000, ge=1, description="最大条目数（LRU 等）")


class RedisSettings(BaseModel):
    """Redis（可选增强；未配置 url 视为未启用）"""

    url: Optional[str] = Field(default=None, description="Redis 连接 URL")
    key_prefix: str = Field(default="th:", description="统一 key 前缀")
    cluster: RedisClusterSettings = Field(default_factory=RedisClusterSettings)
    sentinel: RedisSentinelSettings = Field(default_factory=RedisSentinelSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)


class WorkerSettings(BaseModel):
    """工作进程 / 事件流"""

    event_stream_name: str = Field(default="th_events", description="事件流名称")
    poll_interval: float = Field(default=2.0, gt=0, description="轮询/心跳间隔（秒）")


class LoggingSettings(BaseModel):
    """日志参数"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    format: Literal["console", "json"] = Field(default="console")


class RetryPolicySettings(BaseModel):
    """重试策略"""

    max_attempts: int = Field(default=2, ge=0)
    initial_backoff: float = Field(default=1.0, gt=0)
    max_backoff: float = Field(default=60.0, gt=0)


class QueueSettings(BaseModel):
    """队列 / 事件流路由"""

    kind: Literal["redis", "db"] = Field(default="db", description="队列类型")
    prefix: str = Field(default="th:queue:", description="队列 key 前缀")
    streams_prefix: str = Field(default="th:streams:", description="事件流 key 前缀")


class OpenAISettings(BaseModel):
    """OpenAI 引擎配置（当 active_engine=openai 时使用）"""

    api_key: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(
        default=None, description="自定义网关可设定；默认官方端点"
    )
    model: Optional[str] = Field(default=None, description="如 gpt-4o / gpt-4o-mini")
    temperature: float = Field(default=0.1, ge=0)
    timeout: float = Field(default=60.0, gt=0, description="整体超时（秒）")
    connect_timeout: float = Field(default=5.0, gt=0, description="连接超时（秒）")
    max_retries: int = Field(default=2, ge=0)


class TranslatorsSettings(BaseModel):
    """Translators 引擎配置（预留）"""

    provider: Optional[str] = Field(default=None, description="如 google / deeplx 等")


class DebugEngineSettings(BaseModel):
    """Debug 引擎配置"""

    mode: Literal["SUCCESS", "FAIL"] = Field(default="SUCCESS")
    fail_on_text: Optional[str] = Field(default=None)
    fail_is_retryable: bool = Field(default=True)


class ObservabilitySettings(BaseModel):
    """可观测性/OTEL（预留）"""

    otel_exporter: Optional[str] = Field(
        default=None, description="如 prometheus / jaeger；未实现时忽略"
    )


# ===================== 顶层配置 =====================


class TransHubConfig(BaseSettings):
    """
    Trans-Hub 核心配置（仅值与校验；无副作用）。
    覆盖方式：环境变量前缀 TRANSHUB_；双下划线 "__" 作为嵌套分隔。
    """

    # --- 服务器通用（预留） ---
    debug: bool = Field(default=True, description="是否开启调试模式")
    host: str = Field(default="0.0.0.0", description="服务绑定地址")
    port: int = Field(default=8000, description="服务监听端口")

    # --- 领域子配置 ---
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

    # --- 连接池高级参数（供引擎工厂；可选）---
    db_pool_size: Optional[int] = Field(default=None, ge=1)
    db_max_overflow: Optional[int] = Field(default=None, ge=0)
    db_pool_timeout: int = Field(default=30, ge=1)
    db_pool_recycle: Optional[int] = Field(default=None, ge=1)
    db_pool_pre_ping: bool = Field(default=True)
    db_echo: bool = Field(
        default=False, description="覆盖 database.echo；True 时打印 SQL"
    )

    # --- 维护库（同步驱动，运维建删库用；可选）---
    maintenance_database_url: Optional[str] = Field(
        default=None,
        description=(
            "维护库 DSN（同步驱动，仅允许 postgresql+psycopg）。"
            "未提供且主库为 PG 时自动推导为 postgresql+psycopg://.../postgres"
        ),
    )

    # --- 语言/引擎/批量/GC ---
    default_source_lang: Optional[str] = Field(
        default=None, description="默认源语言（BCP-47）"
    )
    active_engine: Literal["debug", "translators", "openai"] = Field(default="debug")
    batch_size: int = Field(default=50, ge=1)
    gc_retention_days: int = Field(default=90, ge=1)

    # ---------- 校验与自动推导 ----------

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
    def _autofill_maint(cls, v: Optional[str], info):  # type: ignore[override]
        """
        若未显式给出维护库且主库为 Postgres，则自动推导为 psycopg + postgres 库（v3）。
        """
        if v:
            # 同时严格要求维护库驱动正确
            try:
                drv = make_url(v).drivername.lower()
            except Exception as e:
                raise ValueError(f"非法维护库 DSN：{v!r}（{e}）")
            if drv != "postgresql+psycopg":
                raise ValueError(
                    f"维护库驱动需为 'postgresql+psycopg'，实际为：{drv!r}"
                )
            return v

        # Pydantic v2: info.data 包含已解析的同级字段
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

    # ===================== Pydantic v2 设置 =====================
    model_config = {
        "env_nested_delimiter": "__",
        "env_prefix": "TRANSHUB_",
        "case_sensitive": False,
        "extra": "ignore",
        # [修改] 移除静态的 env_file，由 bootstrap 模块动态提供
        "env_file_encoding": "utf-8",
    }


__all__ = [
    "TransHubConfig",
    "DatabaseSettings",
    "RedisSettings",
    "WorkerSettings",
    "LoggingSettings",
    "RetryPolicySettings",
    "QueueSettings",
    "OpenAISettings",
    "TranslatorsSettings",
    "DebugEngineSettings",
    "ObservabilitySettings",
    "CacheSettings",
    "RedisClusterSettings",
    "RedisSentinelSettings",
]

# packages/server/src/trans_hub/config.py
"""
定义 Trans-Hub Server 的所有配置选项（Pydantic v2，遵守技术宪章）。

要点：
- 配置集中在此处，仅提供“值与校验”，不做引擎创建等副作用；
- 支持嵌套配置（database/redis/worker），并提供与历史扁平字段兼容的属性别名：
  - cfg.database_url -> cfg.database.url
  - cfg.redis_url    -> cfg.redis.url
- 自动推导维护库 DSN（Postgres 时缺省推导为 psycopg2 + postgres）
"""

from __future__ import annotations

from typing import Optional

import langcodes
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
from sqlalchemy.engine.url import make_url


# ===================== 嵌套子模型 =====================


class DatabaseSettings(BaseModel):
    """数据库连接配置（主库，异步驱动）"""

    url: str = Field(
        default="postgresql+asyncpg://transhub:transhub@localhost:5432/transhub_dev",
        description="PostgreSQL 异步连接 URL（或 sqlite+aiosqlite://）",
    )

    # 连接池/行为参数（如不需要可保持默认）
    echo: bool = Field(default=False, description="是否输出 SQL 调试日志")


class RedisSettings(BaseModel):
    """Redis 缓存配置（可选）"""

    url: Optional[str] = Field(
        default=None,
        description="Redis 连接 URL；为空表示不启用 Redis",
    )
    key_prefix: str = Field(default="th:", description="统一的 Redis key 前缀")


class WorkerSettings(BaseModel):
    """工作进程/事件流配置"""

    event_stream_name: str = Field(
        default="th_events",
        description="事件流名称（测试环境固定默认即可）",
    )


# ===================== 顶层配置 =====================


class TransHubConfig(BaseSettings):
    """
    Trans-Hub 核心配置。
    - 仅负责“值与校验”，不创建任何外部资源；
    - 通过环境变量覆盖，前缀 TRANSHUB_，嵌套用双下划线分隔（见 model_config）。
    """

    # --- 服务器通用 ---
    debug: bool = Field(default=True, description="是否开启调试模式")
    host: str = Field(default="0.0.0.0", description="服务绑定地址")
    port: int = Field(default=8000, description="服务监听端口")

    # --- 模块化配置 ---
    database: DatabaseSettings = Field(
        default_factory=DatabaseSettings, description="主库配置（异步）"
    )
    redis: RedisSettings = Field(
        default_factory=RedisSettings, description="Redis 配置"
    )
    worker: WorkerSettings = Field(
        default_factory=WorkerSettings, description="工作进程/事件流配置"
    )

    # --- 连接池高级参数（供引擎工厂映射；可选）---
    db_pool_size: Optional[int] = Field(
        default=None, ge=1, description="连接池大小；None=默认"
    )
    db_max_overflow: Optional[int] = Field(
        default=None, ge=0, description="最大溢出连接数；None=默认"
    )
    db_pool_timeout: int = Field(default=30, ge=1, description="获取连接超时（秒）")
    db_pool_recycle: Optional[int] = Field(
        default=None, ge=1, description="连接回收（秒），长连接建议设置"
    )
    db_pool_pre_ping: bool = Field(default=True, description="是否启用 pre_ping")
    db_echo: bool = Field(
        default=False, description="覆盖 database.echo；为 True 时打印 SQL"
    )

    # --- 维护库（同步驱动，运维建删库用；可选）---
    maintenance_database_url: Optional[str] = Field(
        default=None,
        description="维护库 DSN（同步驱动）。未提供且主库为 Postgres 时自动推导为 postgresql+psycopg2://.../postgres",
    )

    # --- 语言/引擎（示例字段，按需扩展）---
    default_source_lang: Optional[str] = Field(
        default=None, description="默认源语言（BCP-47 标签）"
    )
    active_engine: str = Field(default="debug", description="默认翻译引擎标识")

    # ---------- 校验与兼容别名 ----------

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
        """若未显式给出维护库且主库为 Postgres，则自动推导为 psycopg2 + postgres 库。"""
        if v:
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
            return str(url.set(drivername="postgresql+psycopg2", database="postgres"))
        return v

    # ----- 与历史扁平字段兼容的属性别名 -----

    @property
    def database_url(self) -> str:
        """兼容读取主库 DSN：cfg.database_url"""
        return self.database.url

    @property
    def redis_url(self) -> Optional[str]:
        """兼容读取 Redis DSN：cfg.redis_url"""
        return getattr(self.redis, "url", None)

    @property
    def redis_key_prefix(self) -> str:
        # ★ 新增：Coordinator 里会用到
        return self.redis.key_prefix

    # ----- Pydantic v2 配置 -----
    model_config = {
        "env_nested_delimiter": "__",
        "env_prefix": "TRANSHUB_",
        "case_sensitive": False,
        "extra": "ignore",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

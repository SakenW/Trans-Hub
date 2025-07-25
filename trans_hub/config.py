# trans_hub/config.py
"""
定义了 Trans-Hub 项目的主配置模型和相关的子模型。
此版本采用“注册”模式，通过元数据注册表动态发现引擎配置，
从而彻底解除了与引擎模块的循环依赖。
"""

from typing import Any, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from trans_hub.cache import CacheConfig

# 注意：所有引擎配置的导入都已移除。


# ==============================================================================
#  子配置模型
# ==============================================================================


class LoggingConfig(BaseModel):
    """日志系统的配置。."""

    level: str = "INFO"
    format: Literal["json", "console"] = "console"


class RetryPolicyConfig(BaseModel):
    """重试策略的配置。."""

    max_attempts: int = 2
    initial_backoff: float = 1.0
    max_backoff: float = 60.0


class EngineConfigs(BaseModel):
    """一个用于聚合所有已知引擎特定配置的模型。."""

    # 这些字段的类型将在 TransHubConfig 的验证器中被动态填充和验证。
    # 定义为 Any 以避免静态类型问题，实际运行时会是具体的 EngineConfig 模型实例。
    debug: Optional[Any] = None
    translators: Optional[Any] = None
    openai: Optional[Any] = None


# ==============================================================================
#  主配置模型
# ==============================================================================


class TransHubConfig(BaseModel):
    """Trans-Hub 的主配置对象。"""

    database_url: str = "sqlite:///transhub.db"
    active_engine: str = "translators"
    batch_size: int = Field(default=50, description="处理待办任务时的默认批处理大小")
    source_lang: Optional[str] = Field(default=None, description="全局默认的源语言代码")
    gc_retention_days: int = Field(default=90, description="垃圾回收的保留天数")

    cache_config: CacheConfig = Field(default_factory=CacheConfig)
    engine_configs: EngineConfigs = Field(default_factory=EngineConfigs)
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @property
    def db_path(self) -> str:
        """从 database_url 中安全地解析出文件路径。."""
        parsed_url = urlparse(self.database_url)
        if parsed_url.scheme != "sqlite":
            raise ValueError("目前只支持 'sqlite' 数据库 URL。")
        path = parsed_url.netloc or parsed_url.path
        if path.startswith("/") and ":" in path:
            return path[1:]
        return path

    @model_validator(mode="after")
    def _validate_and_autocreate_engine_config(self) -> "TransHubConfig":
        """动态地从元数据注册表中查找并创建引擎配置。"""
        # 动态导入元数据注册表
        # 这是一个关键步骤：通过导入一个高层模块（如 Coordinator），
        # 我们确保 Python 已经加载并执行了 `trans_hub.engines` 包下的所有模块，
        # 从而触发了所有引擎的自我注册逻辑。
        # noqa: F401 (unused-import) is used to signal that this import is intentional
        # for its side effects (triggering module discovery and registration).
        from trans_hub.engine_registry import discover_engines
        from trans_hub.engines.meta import ENGINE_CONFIG_REGISTRY

        discover_engines()

        # 为所有已知的引擎创建默认配置（如果用户没有提供）
        if self.engine_configs.debug is None and "debug" in ENGINE_CONFIG_REGISTRY:
            self.engine_configs.debug = ENGINE_CONFIG_REGISTRY["debug"]()
        if (
            self.engine_configs.translators is None
            and "translators" in ENGINE_CONFIG_REGISTRY
        ):
            self.engine_configs.translators = ENGINE_CONFIG_REGISTRY["translators"]()

        # 检查并按需创建活动引擎的配置
        if getattr(self.engine_configs, self.active_engine, None) is None:
            config_class = ENGINE_CONFIG_REGISTRY.get(self.active_engine)
            if not config_class:
                raise ValueError(
                    f"活动引擎 '{self.active_engine}' 已指定, 但其配置模型未在元数据中注册。"
                )

            # BaseSettings 会自动从 .env 文件加载
            setattr(self.engine_configs, self.active_engine, config_class())

        return self

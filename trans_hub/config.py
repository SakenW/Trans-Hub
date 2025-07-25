# trans_hub/config.py
"""
定义了 Trans-Hub 项目的主配置模型和相关的子模型。
这是所有配置的“单一事实来源”，上层应用应该创建并传递 TransHubConfig 对象。
"""

from typing import TYPE_CHECKING, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from trans_hub.cache import CacheConfig

# 使用 TYPE_CHECKING 块来导入引擎配置类型，
# 这只在静态类型检查期间有效，避免了运行时的循环导入问题。
if TYPE_CHECKING:
    from trans_hub.engines.debug import DebugEngineConfig
    from trans_hub.engines.openai import OpenAIEngineConfig
    from trans_hub.engines.translators_engine import TranslatorsEngineConfig


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

    # 使用字符串前向引用 ("...") 来声明类型。
    # 这推迟了类型的实际解析，是解决循环依赖的关键。
    debug: Optional["DebugEngineConfig"] = None
    translators: Optional["TranslatorsEngineConfig"] = None
    openai: Optional["OpenAIEngineConfig"] = None


# ==============================================================================
#  主配置模型
# ==============================================================================


class TransHubConfig(BaseModel):
    """
    Trans-Hub 的主配置对象。
    这是初始化 Coordinator 时需要传入的核心配置。
    """

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
        """只为 active_engine 创建配置（如果尚未提供），以避免不必要的依赖问题。"""
        # 在运行时动态导入，以避免模块顶部的循环依赖
        from trans_hub.engine_registry import ENGINE_REGISTRY

        # 确保 Pydantic 模型已解析好前向引用
        self.engine_configs.model_rebuild(force=True)

        # 只检查并按需创建 *活动引擎* 的配置
        if getattr(self.engine_configs, self.active_engine, None) is None:
            engine_class = ENGINE_REGISTRY.get(self.active_engine)
            if not engine_class:
                raise ValueError(
                    f"活动引擎 '{self.active_engine}' 已指定, 但在引擎注册表中找不到对应的引擎类。"
                )
            # 自动创建配置实例 (BaseSettings 会从 .env 加载)
            setattr(
                self.engine_configs, self.active_engine, engine_class.CONFIG_MODEL()
            )

        return self


# 在文件末尾，为所有使用了前向引用的模型更新引用。
# 这对 mypy 和 Pydantic v2 都很重要，以确保类型提示被正确解析。
if TYPE_CHECKING:
    from trans_hub.engines.debug import DebugEngineConfig
    from trans_hub.engines.openai import OpenAIEngineConfig
    from trans_hub.engines.translators_engine import TranslatorsEngineConfig

    EngineConfigs.model_rebuild()

# trans_hub/config.py
"""
定义了 Trans-Hub 项目的主配置模型和相关的子模型。
这是所有配置的“单一事实来源”，上层应用应该创建并传递 TransHubConfig 对象。
"""

from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from trans_hub.cache import CacheConfig

# 注意：引擎配置的导入已从这里移除，以避免循环依赖
# 它们将在 model_validator 中被动态导入


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

    # 在运行时，这些字段的类型将由 model_validator 动态填充
    debug: Optional[BaseModel] = None
    translators: Optional[BaseModel] = None
    openai: Optional[BaseModel] = None


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
    def validate_and_autocreate_engine_config(self) -> "TransHubConfig":
        """
        验证活动的引擎是否在配置中定义，如果未定义，则尝试自动创建。
        [最终优化] 此版本动态地从 ENGINE_REGISTRY 查找配置模型，无需硬编码。
        """
        # 在运行时动态导入，以避免模块顶部的循环依赖
        from trans_hub.engine_registry import ENGINE_REGISTRY

        # 确保默认引擎的配置实例存在
        if self.engine_configs.debug is None:
            engine_class = ENGINE_REGISTRY.get("debug")
            if engine_class:
                self.engine_configs.debug = engine_class.CONFIG_MODEL()

        if self.engine_configs.translators is None:
            engine_class = ENGINE_REGISTRY.get("translators")
            if engine_class:
                self.engine_configs.translators = engine_class.CONFIG_MODEL()

        # 检查并按需创建活动引擎的配置
        active_config = getattr(self.engine_configs, self.active_engine, None)
        if active_config is None:
            engine_class = ENGINE_REGISTRY.get(self.active_engine)
            if not engine_class:
                raise ValueError(
                    f"活动引擎 '{self.active_engine}' 已指定, 但在引擎注册表中找不到对应的引擎类。"
                )

            config_class = engine_class.CONFIG_MODEL
            setattr(self.engine_configs, self.active_engine, config_class())

        return self

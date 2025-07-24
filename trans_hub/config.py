# trans_hub/config.py (最终优化版)
"""定义了 Trans-Hub 项目的主配置模型和相关的子模型。
这是所有配置的“单一事实来源”，上层应用应该创建并传递 TransHubConfig 对象。.
"""

from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings

from trans_hub.cache import CacheConfig
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

    debug: Optional[DebugEngineConfig] = Field(default_factory=DebugEngineConfig)
    translators: Optional[TranslatorsEngineConfig] = Field(
        default_factory=TranslatorsEngineConfig
    )
    # openai 默认为 None，将由 TransHubConfig 的智能验证器按需创建
    openai: Optional[OpenAIEngineConfig] = None


# ==============================================================================
#  主配置模型
# ==============================================================================


class TransHubConfig(BaseModel):
    """Trans-Hub 的主配置对象。
    这是初始化 Coordinator 时需要传入的核心配置。.
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

    # --- 核心修正 1：添加一个便捷属性来获取数据库文件路径 ---
    @property
    def db_path(self) -> str:
        """从 database_url 中安全地解析出文件路径。."""
        parsed_url = urlparse(self.database_url)
        if parsed_url.scheme != "sqlite":
            raise ValueError("目前只支持 'sqlite' 数据库 URL。")
        # urlparse('sqlite:///path') -> netloc='', path='/path'
        # urlparse('sqlite://path') -> netloc='path', path=''
        # 因此，优先使用 netloc，然后是 path
        path = parsed_url.netloc or parsed_url.path
        # 移除 Windows 驱动器号前的斜杠，例如 /C:/... -> C:/...
        if path.startswith("/") and ":" in path:
            return path[1:]
        return path

    # --- 核心修正 2：使用更强大的 model_validator 来智能处理引擎配置 ---
    @model_validator(mode="after")
    def validate_and_autocreate_engine_config(self) -> "TransHubConfig":
        """验证活动的引擎是否在配置中定义，如果未定义，则尝试自动创建。
        这极大地改善了用户体验。.
        """
        active_config = getattr(self.engine_configs, self.active_engine, None)

        if active_config is None:
            # 尝试找到对应的配置类
            engine_name_to_config_class = {
                "debug": DebugEngineConfig,
                "translators": TranslatorsEngineConfig,
                "openai": OpenAIEngineConfig,
            }

            config_class = engine_name_to_config_class.get(self.active_engine)

            if config_class:
                # 如果是 BaseSettings 的子类，它会自动从 .env 加载
                if issubclass(config_class, BaseSettings):
                    # 自动创建实例
                    setattr(self.engine_configs, self.active_engine, config_class())
                else:
                    # 对于非 BaseSettings 的配置，也创建一个默认实例
                    setattr(self.engine_configs, self.active_engine, config_class())
            else:
                raise ValueError(
                    f"活动引擎 '{self.active_engine}' 已指定, 但无法找到其对应的配置模型类。"
                )
        return self

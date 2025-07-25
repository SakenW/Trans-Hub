# trans_hub/config.py
"""
定义了 Trans-Hub 项目的主配置模型和相关的子模型。
此版本采用完全动态的配置模式，无需硬编码任何引擎名称。
"""

from typing import Any, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trans_hub.cache import CacheConfig


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: Literal["json", "console"] = "console"


class RetryPolicyConfig(BaseModel):
    max_attempts: int = 2
    initial_backoff: float = 1.0
    max_backoff: float = 60.0


class EngineConfigs(BaseModel):
    """
    一个用于聚合所有引擎特定配置的基础模型。
    它允许存在任意未在此处声明的字段。
    """

    model_config = ConfigDict(extra="allow")


class TransHubConfig(BaseModel):
    """Trans-Hub 的主配置对象。"""

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
        parsed_url = urlparse(self.database_url)
        if parsed_url.scheme != "sqlite":
            raise ValueError("目前只支持 'sqlite' 数据库 URL。")
        path = parsed_url.netloc or parsed_url.path
        if path.startswith("/") and ":" in path:
            return path[1:]
        return path

    @model_validator(mode="before")
    @classmethod
    def _prepare_dynamic_engine_configs(cls, data: Any) -> Any:
        """在 Pydantic 开始验证之前，动态地构建并注入类型完整的 EngineConfigs 模型。"""
        if not isinstance(data, dict):
            return data

        from trans_hub.engine_registry import discover_engines

        discover_engines()

        from pydantic import create_model

        from trans_hub.engines.meta import ENGINE_CONFIG_REGISTRY

        # 动态地为所有已注册的引擎创建字段定义
        dynamic_fields: dict[str, Any] = {
            name: (Optional[config_class], None)
            for name, config_class in ENGINE_CONFIG_REGISTRY.items()
        }

        # 创建一个临时的、类型完全定义的 DynamicEngineConfigs 模型
        DynamicEngineConfigs = create_model(  # noqa: N806
            "DynamicEngineConfigs",
            **dynamic_fields,
            __base__=EngineConfigs,
        )

        # 在 TransHubConfig 自己的字段定义中，用这个动态模型替换掉原来的 EngineConfigs
        # 这样 Pydantic 在后续验证中就会使用这个类型更精确的模型
        cls.model_fields["engine_configs"].annotation = DynamicEngineConfigs

        return data

    @model_validator(mode="after")
    def _autocreate_engine_instances(self) -> "TransHubConfig":
        """在验证之后，为引擎创建配置实例。"""
        from trans_hub.engine_registry import discover_engines

        discover_engines()
        from trans_hub.engines.meta import ENGINE_CONFIG_REGISTRY

        # 为所有已注册的引擎创建默认实例（如果用户没有提供）
        for name, config_class in ENGINE_CONFIG_REGISTRY.items():
            if getattr(self.engine_configs, name, None) is None:
                instance = config_class()
                setattr(self.engine_configs, name, instance)

        # 确保活动引擎的配置一定存在
        if getattr(self.engine_configs, self.active_engine, None) is None:
            raise ValueError(f"活动引擎 '{self.active_engine}' 的配置未能被创建。")
        return self

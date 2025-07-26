# trans_hub/config.py
"""
定义了 Trans-Hub 项目的主配置模型和相关的子模型。
此版本采用“注册”模式，并实现了完全动态的配置解析和重建，
无需硬编码任何引擎配置的导入。
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
    """一个用于聚合所有引擎特定配置的基础模型，允许未知字段。"""
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
        """
        在 Pydantic 开始验证之前，动态地构建并注入一个类型完整的 EngineConfigs 模型。
        这使得 mypy 和运行时都能正确理解 engine_configs 的结构。
        """
        if not isinstance(data, dict):
            return data

        from trans_hub.engine_registry import discover_engines
        discover_engines()

        from pydantic import create_model
        from trans_hub.engines.meta import ENGINE_CONFIG_REGISTRY

        dynamic_fields: dict[str, Any] = {
            name: (Optional[config_class], None)
            for name, config_class in ENGINE_CONFIG_REGISTRY.items()
        }

        DynamicEngineConfigs = create_model(
            "DynamicEngineConfigs",
            **dynamic_fields,
            __base__=EngineConfigs,
        )
        
        # 替换 TransHubConfig 中 EngineConfigs 的类型注解
        cls.model_fields['engine_configs'].annotation = DynamicEngineConfigs

        return data

    @model_validator(mode="after")
    def _autocreate_active_engine_config(self) -> "TransHubConfig":
        """在验证之后，只为 active_engine 创建配置实例（如果需要）。"""
        from trans_hub.engines.meta import ENGINE_CONFIG_REGISTRY

        # 检查并按需创建 *活动引擎* 的配置
        if getattr(self.engine_configs, self.active_engine, None) is None:
            config_class = ENGINE_CONFIG_REGISTRY.get(self.active_engine)
            if not config_class:
                raise ValueError(
                    f"活动引擎 '{self.active_engine}' 已指定, 但其配置模型未在元数据中注册。"
                )
            setattr(self.engine_configs, self.active_engine, config_class())
        
        return self
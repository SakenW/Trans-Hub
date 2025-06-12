"""
trans_hub/config.py

定义了 Trans-Hub 项目的主配置模型和相关的子模型。
这是配置的“单一事实来源”，上层应用应该创建并传递这个对象。
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field

# 导入所有可能用到的引擎配置模型
from trans_hub.engines.debug import DebugEngineConfig # [新] 导入 DebugEngineConfig
from trans_hub.engines.openai import OpenAIEngineConfig
# from trans_hub.engines.deepl import DeepLEngineConfig # 未来可以取消注释


class LoggingConfig(BaseModel):
    """日志系统的配置。"""
    level: str = "INFO"
    format: Literal["json", "console"] = "console"


class RetryPolicyConfig(BaseModel):
    """重试策略的配置。"""
    max_attempts: int = 3
    initial_backoff: float = 1.0
    max_backoff: float = 60.0
    jitter: bool = True


class EngineConfigs(BaseModel):
    """一个用于聚合所有引擎特定配置的模型。"""
    # [新] 为 debug 引擎添加配置字段
    debug: Optional[DebugEngineConfig] = Field(default_factory=DebugEngineConfig)

    # 每个引擎的配置都是可选的，因为用户可能只使用其中一个
    openai: Optional[OpenAIEngineConfig] = None
    # deepl: Optional[DeepLEngineConfig] = None
    # ... 未来可以在此添加更多引擎配置


class TransHubConfig(BaseModel):
    """
    Trans-Hub 的主配置对象。
    上层应用应该创建这个模型的实例，并将其传递给 Coordinator。
    """
    # 数据库连接字符串，例如 "sqlite:///my_translations.db"
    database_url: str
    
    # 当前要激活使用的引擎的名称 (必须与 EngineConfigs中的字段名匹配)
    active_engine: str
    
    # 包含所有引擎配置的嵌套模型
    engine_configs: EngineConfigs
    
    # 重试和日志记录策略，提供合理的默认值
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
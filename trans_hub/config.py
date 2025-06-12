"""
trans_hub/config.py (v1.0 Final)

定义了 Trans-Hub 项目的主配置模型和相关的子模型。
这是所有配置的“单一事实来源”，上层应用应该创建并传递 TransHubConfig 对象。
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field

# 导入所有已实现的引擎的配置模型
from trans_hub.engines.debug import DebugEngineConfig
from trans_hub.engines.openai import OpenAIEngineConfig
from trans_hub.engines.translators_engine import TranslatorsEngineConfig


# ==============================================================================
#  策略配置模型 (未来可扩展)
# ==============================================================================

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


# ==============================================================================
#  引擎配置聚合模型
# ==============================================================================

class EngineConfigs(BaseModel):
    """
    一个用于聚合所有已知引擎特定配置的模型。
    Coordinator 会根据 active_engine 的名称，在这里查找对应的配置。
    """
    # 字段名必须与引擎在注册表中的小写名称完全匹配。
    
    # DebugEngine 的配置。
    # 使用 default_factory 确保即使不提供配置，也会创建一个默认实例。
    debug: Optional[DebugEngineConfig] = Field(default_factory=DebugEngineConfig)
    
    # TranslatorsEngine 的配置。
    # 同样使用 default_factory，使其成为真正的“开箱即用”默认引擎。
    translators: Optional[TranslatorsEngineConfig] = Field(default_factory=TranslatorsEngineConfig)
    
    # OpenAI 引擎的配置。
    # 默认为 None，因为使用它需要用户明确提供 .env 配置。
    openai: Optional[OpenAIEngineConfig] = None
    
    # 未来可以在此添加更多引擎配置，例如：
    # deepl: Optional[DeepLEngineConfig] = None


# ==============================================================================
#  主配置模型
# ==============================================================================

class TransHubConfig(BaseModel):
    """
    Trans-Hub 的主配置对象。
    这是初始化 Coordinator 时需要传入的核心配置。
    """
    # [必需] 数据库连接字符串，例如 "sqlite:///my_translations.db"
    database_url: str
    
    # [核心变更] 当前要激活使用的引擎的名称。
    # 默认值已设置为 'translators'，为用户提供开箱即用的免费翻译功能。
    active_engine: str = "translators"
    
    # 包含所有引擎配置的嵌套模型。
    # 使用 default_factory 确保即使不提供，也会创建一个包含默认引擎配置的实例。
    engine_configs: EngineConfigs = Field(default_factory=EngineConfigs)
    
    # 重试和日志记录策略，提供合理的默认值。
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
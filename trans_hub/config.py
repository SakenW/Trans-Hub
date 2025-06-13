# trans_hub/config.py (v1.1 修正版)
"""
定义了 Trans-Hub 项目的主配置模型和相关的子模型。
这是所有配置的“单一事实来源”，上层应用应该创建并传递 TransHubConfig 对象。
"""
from typing import Literal, Optional

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
    """一个用于聚合所有已知引擎特定配置的模型。
    Coordinator 会根据 active_engine 的名称，在这里查找对应的配置。
    """

    # 字段名必须与引擎在注册表中的小写名称完全匹配。
    debug: Optional[DebugEngineConfig] = Field(default_factory=DebugEngineConfig)
    translators: TranslatorsEngineConfig = (
        Field(  # <-- 修正点：将 TranslatorsEngineConfig 设为非 Optional，并作为默认
            default_factory=TranslatorsEngineConfig
        )
    )
    openai: Optional[OpenAIEngineConfig] = None


# ==============================================================================
#  主配置模型
# ==============================================================================


class TransHubConfig(BaseModel):
    """Trans-Hub 的主配置对象。
    这是初始化 Coordinator 时需要传入的核心配置。
    """

    database_url: str = "sqlite:///transhub.db"  # 默认值，方便测试
    active_engine: str = "translators"
    engine_configs: EngineConfigs = Field(default_factory=EngineConfigs)
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    # 修正点：添加 gc_retention_days 字段，并提供默认值
    gc_retention_days: int = Field(default=30, description="垃圾回收的保留天数")

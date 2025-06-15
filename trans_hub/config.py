# trans_hub/config.py
"""
定义了 Trans-Hub 项目的主配置模型和相关的子模型。
这是所有配置的“单一事实来源”，上层应用应该创建并传递 TransHubConfig 对象。
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationInfo, field_validator

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

    max_attempts: int = 2  # 默认重试2次 (总共尝试3次)
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
    translators: Optional[TranslatorsEngineConfig] = Field(
        default_factory=TranslatorsEngineConfig
    )
    openai: Optional[OpenAIEngineConfig] = None


# ==============================================================================
#  主配置模型
# ==============================================================================


class TransHubConfig(BaseModel):
    """Trans-Hub 的主配置对象。
    这是初始化 Coordinator 时需要传入的核心配置。
    """

    database_url: str = "sqlite:///transhub.db"
    active_engine: str = "translators"

    # 新增: batch_size 字段，修复 AttributeError
    batch_size: int = Field(default=50, description="处理待办任务时的默认批处理大小")

    # 新增: source_lang 字段，用于需要源语言的引擎
    source_lang: Optional[str] = Field(
        default=None,
        description="全局默认的源语言代码，如果提供，将传递给引擎",
    )

    engine_configs: EngineConfigs = Field(default_factory=EngineConfigs)
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    gc_retention_days: int = Field(default=90, description="垃圾回收的保留天数")

    @field_validator("active_engine")
    @classmethod
    def validate_active_engine(cls, v: str, info: ValidationInfo) -> str:
        """验证活动的引擎是否在配置中定义。"""
        # Pydantic v2 中，上下文通过 info.context 访问，但这里我们用 info.data
        if "engine_configs" in info.data:
            engine_configs = info.data["engine_configs"]
            if not getattr(engine_configs, v, None):
                raise ValueError(
                    f"活动引擎 '{v}' 已指定, 但在 'engine_configs' 中未找到其配置对象。"
                )
        return v

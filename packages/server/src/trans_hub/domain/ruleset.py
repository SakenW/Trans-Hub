# src/trans_hub/domain/ruleset.py
"""
定义与规则包 (Ruleset) 和 Linting 相关的领域模型。
这部分目前为架构占位，为未来的规则引擎功能提供基础。
"""
from enum import Enum

from pydantic import BaseModel


class RuleSeverity(str, Enum):
    """规则的严重性级别。"""
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


class RuleSelector(str, Enum):
    """规则作用于源文本、译文还是两者。"""
    SOURCE = "source"
    TRANSLATION = "translation"
    BOTH = "both"


class Rule(BaseModel):
    """
    表示一条具体的 Linting 规则。
    """
    key: str
    severity: RuleSeverity = RuleSeverity.WARN
    selector: RuleSelector = RuleSelector.TRANSLATION
    pattern: str | None = None
    message: str
    enabled: bool = True


class Ruleset(BaseModel):
    """
    表示一组规则的集合，通常应用于特定的范围（如项目、语言）。
    """
    scope: str
    rules: list[Rule]
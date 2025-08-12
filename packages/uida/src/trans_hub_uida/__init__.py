# src/trans_hub_uida/__init__.py
"""
Trans-Hub UIDA (统一标识符架构) 标准实现包。

本包提供了生成、编码和处理 UIDA 的所有核心工具，是系统身份识别的
唯一真理源。它是一个纯逻辑包，没有任何外部 I/O 依赖。

主要导出:
- `generate_uida`: 核心函数，用于从 keys 生成 UIDA 的所有组件。
- `UIDAComponents`: 包含 UIDA 各种形式的数据类。
- `CanonicalizationError`: 当输入不满足 I-JSON 规范时抛出的异常。
"""
from .uida import CanonicalizationError, UIDAComponents, generate_uida

__all__ = ["generate_uida", "CanonicalizationError", "UIDAComponents"]
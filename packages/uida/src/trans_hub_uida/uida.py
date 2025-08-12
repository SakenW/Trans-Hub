# src/trans_hub_uida/uida.py
"""
UIDA 编码器、I-JSON 守卫和 RFC 8785 规范化逻辑的实现。
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, NamedTuple

import rfc8785


class CanonicalizationError(ValueError):
    """当输入不满足 I-JSON 或 JCS 规范化失败时抛出。"""


class UIDAComponents(NamedTuple):
    """
    封装了 UIDA 的所有派生组件。

    Attributes:
        keys_b64: JCS(keys) 的 Base64URL 编码字符串。
        keys_sha256_bytes: JCS(keys) 的 32 字节 SHA-256 哈希摘要。
        canonical_bytes: JCS(keys) 的原始 UTF-8 字节序列。
    """
    keys_b64: str
    keys_sha256_bytes: bytes
    canonical_bytes: bytes


def _assert_i_json_compat(value: Any, path: str = "$") -> None:
    """
    递归检查输入对象是否符合 I-JSON 规范。
    I-JSON 是 JSON 的一个严格子集，确保了跨平台的最大互操作性。
    主要规则：禁止 float、非字符串键等。
    """
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise CanonicalizationError(
                    f"I-JSON 校验失败: 对象键必须为字符串，但在路径 '{path}' 发现 {type(k)} 类型"
                )
            _assert_i_json_compat(v, f"{path}.{k}")
        return
    if isinstance(value, list):
        for i, v in enumerate(value):
            _assert_i_json_compat(v, f"{path}[{i}]")
        return
    if isinstance(value, (str, int, bool)) or value is None:
        return
    if isinstance(value, float):
        raise CanonicalizationError(f"I-JSON 校验失败: 禁止在 keys 中使用浮点数，路径: '{path}'")
    raise CanonicalizationError(
        f"I-JSON 校验失败: 不支持的类型 {type(value)}，路径: '{path}'"
    )


def generate_uida(keys: dict[str, Any]) -> UIDAComponents:
    """
    从给定的 `keys` 字典生成 UIDA 的所有组件。

    本函数是 UIDA 生成的唯一真理来源，它执行以下步骤：
    1. 校验 `keys` 是否符合 I-JSON 规范。
    2. 使用 RFC 8785 (JCS) 将 `keys` 规范化为确定性的字节序列。
    3. 计算规范化字节的 SHA-256 哈希。
    4. 计算规范化字节的 Base64URL 编码。

    Args:
        keys: 一个符合 I-JSON 规范的字典，用于唯一标识一个内容条目。

    Returns:
        一个 `UIDAComponents` 命名元组，包含所有派生组件。

    Raises:
        CanonicalizationError: 如果 `keys` 不符合 I-JSON 规范或 JCS 序列化失败。
    """
    _assert_i_json_compat(keys)
    try:
        # separators 和 sort_keys 是为了保证确定性输出，rfc8785 内部已经处理了
        canonical_bytes = rfc8785.dumps(keys)
    except Exception as e:
        raise CanonicalizationError(f"JCS 规范化失败: {e}") from e

    sha_bytes = hashlib.sha256(canonical_bytes).digest()
    # urlsafe_b64encode 产生的 '=' 是填充，可以安全移除
    b64_str = base64.urlsafe_b64encode(canonical_bytes).rstrip(b"=").decode("ascii")

    return UIDAComponents(
        keys_b64=b64_str,
        keys_sha256_bytes=sha_bytes,
        canonical_bytes=canonical_bytes,
    )
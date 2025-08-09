# trans_hub/_uida/encoder.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import hashlib
from typing import Any

# 优先使用 C 语言实现的 rfc8785，性能更优
try:
    import rfc8785 as _rfc8785
except ImportError:
    _rfc8785 = None

# 如果 rfc8785 不可用，回退到纯 Python 实现的 jcs
if _rfc8785 is None:
    try:
        import jcs as _jcs
    except ImportError:
        _jcs = None


class CanonicalizationError(RuntimeError):
    """当输入不满足 I-JSON 或找不到 RFC8785/JCS 实现时抛出。"""


def _assert_i_json_compat(value: Any, path: str = "$") -> None:
    """
    I-JSON 守卫：
    - 仅允许 dict/list/str/int/bool/None
    - 禁止 float / NaN / Infinity / 非字符串键
    """
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise CanonicalizationError(
                    f"{path}: object key must be str, got {type(k)}"
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
        raise CanonicalizationError(f"{path}: float is not allowed in keys")
    raise CanonicalizationError(f"{path}: unsupported type {type(value)}")


def _canonical_bytes(payload: Any) -> bytes:
    """将对象按 RFC 8785 / JCS 规范化为 UTF-8 字节串。"""
    if _rfc8785 is not None:
        return _rfc8785.canonicalize(payload)
    if _jcs is not None:
        return _jcs.canonicalize(payload)
    raise CanonicalizationError(
        "No RFC 8785 implementation found (install with 'uida' extra: pip install 'trans-hub[uida]')"
    )


def generate_uid_components(
    keys: dict[str, Any]
) -> tuple[str, bytes, bytes]:
    """
    规范化入口（唯一真理源）。

    对输入的 keys 字典进行 I-JSON 兼容性检查和 RFC 8785 规范化。

    Returns:
        一个元组 (keys_b64, canonical_bytes, sha256_bytes)
    """
    _assert_i_json_compat(keys, "$.keys")
    canonical_bytes = _canonical_bytes(keys)
    b64 = base64.urlsafe_b64encode(canonical_bytes).rstrip(b"=").decode("ascii")
    sha = hashlib.sha256(canonical_bytes).digest()
    return b64, canonical_bytes, sha


def get_canonical_json_for_debug(keys: dict[str, Any]) -> str:
    """返回 JCS 文本（用于日志与排错）。"""
    _assert_i_json_compat(keys)
    return _canonical_bytes(keys).decode("utf-8")
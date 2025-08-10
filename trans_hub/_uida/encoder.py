# trans_hub/_uida/encoder.py
from __future__ import annotations

import base64
import hashlib
from typing import Any


class CanonicalizationError(RuntimeError):
    """当输入不满足 I-JSON 或找不到 RFC8785 实现时抛出。"""


def _assert_i_json_compat(value: Any, path: str = "$") -> None:
    """I-JSON 守卫"""
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
    """将对象按 RFC 8785 (JCS) 规范化为 UTF-8 字节串。"""
    try:
        # [最终修正] 唯一、正确地使用 rfc8785 库
        import rfc8785

        return rfc8785.dumps(payload)
    except ImportError:
        raise CanonicalizationError(
            "JCS implementation 'rfc8785' not found. Install with 'uida' extra: pip install 'trans-hub[uida]'"
        ) from None
    except Exception as e:
        # 捕获 rfc8785 库内部可能抛出的其他错误 (如类型错误)
        raise CanonicalizationError(f"JCS canonicalization failed: {e}") from e


def generate_uid_components(keys: dict[str, Any]) -> tuple[str, bytes, bytes]:
    """规范化入口（唯一真理源）。"""
    _assert_i_json_compat(keys, "$.keys")
    canonical_bytes = _canonical_bytes(keys)
    b64 = base64.urlsafe_b64encode(canonical_bytes).rstrip(b"=").decode("ascii")
    sha = hashlib.sha256(canonical_bytes).digest()
    return b64, canonical_bytes, sha


def get_canonical_json_for_debug(keys: dict[str, Any]) -> str:
    """返回 JCS 文本（用于日志与排错）。"""
    _assert_i_json_compat(keys)
    return _canonical_bytes(keys).decode("utf-8")

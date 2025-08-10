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


# --- Merged from: trans_hub/_uida/reuse_key.py ---
# trans_hub/_uida/reuse_key.py
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

# 预编译正则表达式以提高性能
RE_MAJOR_VERSION = re.compile(r"^(\d+)")
RE_MAJOR_MINOR_VERSION = re.compile(r"^(\d+\.\d+)")


def _normalize_version(value: str, mode: str) -> str:
    """
    根据指定模式对版本字符串进行归一化。

    Args:
        value: 原始版本字符串。
        mode: "major" 或 "major_minor"。

    Returns:
        归一化后的版本字符串。

    """
    if not isinstance(value, str):
        return value

    if mode == "major":
        match = RE_MAJOR_VERSION.match(value)
        return match.group(1) if match else value
    if mode == "major_minor":
        match = RE_MAJOR_MINOR_VERSION.match(value)
        return match.group(1) if match else value
    return value


def reduce_keys_for_reuse(
    keys: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    """
    根据复用策略对 keys 字典进行降维，以生成用于 TM 查找的键。

    Args:
        keys: 原始的 UIDA keys 字典。
        policy: 从 namespace_registry.json 获取的复用策略。

    Returns:
        降维后的 keys 字典。

    """
    if policy.get("strict", False):
        return keys

    ignore_fields = set(policy.get("ignore_fields", []))
    normalize_config = policy.get("normalize", {})

    reduced_keys: dict[str, Any] = {}
    for key, value in keys.items():
        if key in ignore_fields:
            continue
        if key in normalize_config:
            value = _normalize_version(value, normalize_config[key])
        reduced_keys[key] = value

    return reduced_keys


def build_reuse_sha256(
    *, namespace: str, reduced_keys: dict[str, Any], source_fields: dict[str, Any]
) -> bytes:
    r"""
    构建用于在翻译记忆库 (TM) 中查找的复用键。

    复用键 = SHA256( namespace + '\n' + JSON(reduced_keys) + '\n' + JSON(source_fields) )

    Args:
        namespace: 内容的命名空间。
        reduced_keys: 经过策略降维后的 keys。
        source_fields: 从源 payload 中提取的、参与复用判定的字段。

    Returns:
        32字节的 SHA-256 哈希摘要字节串。

    """
    # 使用稳定的 JSON 序列化，确保无论 dict 顺序如何，结果都一样
    # 使用 ensure_ascii=False 以正确处理多语言字符
    # 使用 separators 来移除空白，减小体积
    try:
        reduced_keys_json = json.dumps(
            reduced_keys, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        source_fields_json = json.dumps(
            source_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except TypeError as e:
        raise ValueError(f"无法序列化用于复用键的字典: {e}") from e

    # 将所有部分用换行符连接，形成一个唯一的、规范化的字符串
    blob = f"{namespace}\n{reduced_keys_json}\n{source_fields_json}".encode()

    return hashlib.sha256(blob).digest()

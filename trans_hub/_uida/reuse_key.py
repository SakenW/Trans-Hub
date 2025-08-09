# trans_hub/_uida/reuse_key.py
# -*- coding: utf-8 -*-
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
    """
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
    blob = f"{namespace}\n{reduced_keys_json}\n{source_fields_json}".encode("utf-8")

    return hashlib.sha256(blob).digest()
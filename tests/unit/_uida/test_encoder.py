# tests/unit/_uida/test_encoder.py
"""测试 UIDA 编码器、I-JSON 守卫和 RFC 8785 规范化逻辑。"""
from __future__ import annotations

import base64
import hashlib

import pytest

from trans_hub._uida.encoder import (
    CanonicalizationError,
    generate_uid_components,
    get_canonical_json_for_debug,
)


@pytest.fixture
def keys_a() -> dict[str, str | int]:
    """提供一个标准的 keys 字典。"""
    return {"view": "main_page", "id": "submit_button", "version": 1}


@pytest.fixture
def keys_b() -> dict[str, int | str]:
    """提供一个与 keys_a 逻辑等价但顺序不同的字典。"""
    return {"id": "submit_button", "version": 1, "view": "main_page"}


def test_permutation_invariance(keys_a, keys_b):
    """
    [核心验证] 测试 JCS/RFC 8785 的置换不变性。
    不同顺序的等价字典必须产生完全相同的 UIDA 组件。
    """
    b64_a, bytes_a, sha_a = generate_uid_components(keys_a)
    b64_b, bytes_b, sha_b = generate_uid_components(keys_b)

    assert b64_a == b64_b
    assert bytes_a == bytes_b
    assert sha_a == sha_b
    assert get_canonical_json_for_debug(keys_a) == get_canonical_json_for_debug(keys_b)


def test_jcs_official_vectors():
    """
    [最终修正] 使用 RFC 8785 官方或社区的测试向量，确保 JCS 实现的正确性。
    """
    # 向量 1: 简单对象
    obj1 = {"a": 1, "b": 2}
    expected1 = b'{"a":1,"b":2}'
    assert get_canonical_json_for_debug(obj1).encode('utf-8') == expected1

    # 向量 2: 键排序
    obj2 = {"b": 2, "a": 1}
    assert get_canonical_json_for_debug(obj2).encode('utf-8') == expected1

    # 向量 3: Unicode 和特殊字符转义
    obj3 = {"a": "✓", "b": "\u000c\r"}
    expected3 = b'{"a":"\\u2713","b":"\\f\\r"}'
    assert get_canonical_json_for_debug(obj3).encode('utf-8') == expected3

    # 向量 4: 深度嵌套
    obj4 = {"c": {"a": 1, "b": 2}, "d": [3, 4]}
    expected4 = b'{"c":{"a":1,"b":2},"d":[3,4]}'
    assert get_canonical_json_for_debug(obj4).encode('utf-8') == expected4


def test_output_format_and_content(keys_a):
    """验证 UIDA 组件的格式、类型和内容是否正确。"""
    b64, cano_bytes, sha_bytes = generate_uid_components(keys_a)

    assert isinstance(b64, str)
    assert isinstance(cano_bytes, bytes)
    assert isinstance(sha_bytes, bytes)

    # SHA-256 必须是 32 字节
    assert len(sha_bytes) == 32
    # Base64URL 编码不应包含 '+' 或 '/'
    assert "+" not in b64
    assert "/" not in b64

    # Base64 解码后应与规范化字节串一致
    padding = "=" * (-len(b64) % 4)
    decoded_bytes = base64.urlsafe_b64decode(b64 + padding)
    assert decoded_bytes == cano_bytes


def test_i_json_guard_rejects_invalid_types():
    """验证 I-JSON 守卫能否正确拒绝不兼容的类型。"""
    invalid_key_sets = [
        {"value": 1.23},  # 禁止 float
        {"value": float("nan")},  # 禁止 NaN
        {"value": float("inf")},  # 禁止 Infinity
        {123: "value"},  # 禁止非字符串键
        {"nested": {"value": 3.14}},  # 禁止嵌套 float
    ]

    for keys in invalid_key_sets:
        with pytest.raises(CanonicalizationError):
            generate_uid_components(keys)


def test_i_json_guard_accepts_valid_types():
    """验证 I-JSON 守卫能否正确接受所有兼容的类型。"""
    valid_keys = {
        "a_string": "hello",
        "an_int": 123,
        "a_bool": True,
        "a_none": None,
        "a_list": ["a", 1, False, None, {"nested": True}],
    }
    try:
        generate_uid_components(valid_keys)
    except CanonicalizationError as e:
        pytest.fail(f"I-JSON 守卫错误地拒绝了有效的 keys: {e}")
# packages/uida/tests/unit/test_uida.py
"""
对 trans-hub-uida 包的核心功能进行单元测试。
"""
import base64
import pytest
from trans_hub_uida import CanonicalizationError, generate_uida, UIDAComponents

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
    uida_a = generate_uida(keys_a)
    uida_b = generate_uida(keys_b)
    assert uida_a == uida_b, "不同顺序的等价字典必须产生相同的 UIDA 组件"

def test_output_format_and_content(keys_a):
    """验证 UIDA 组件的格式、类型和内容是否正确。"""
    uida = generate_uida(keys_a)
    assert isinstance(uida, UIDAComponents)
    assert isinstance(uida.keys_b64, str)
    assert isinstance(uida.canonical_bytes, bytes)
    assert isinstance(uida.keys_sha256_bytes, bytes)
    assert len(uida.keys_sha256_bytes) == 32, "SHA-256 哈希必须是 32 字节"
    assert "+" not in uida.keys_b64 and "/" not in uida.keys_b64, "Base64URL 编码不应包含 '+' 或 '/'"

    padding = b"=" * (-len(uida.keys_b64) % 4)
    decoded_bytes = base64.urlsafe_b64decode(uida.keys_b64.encode("ascii") + padding)
    assert decoded_bytes == uida.canonical_bytes, "Base64 解码后应与规范化字节串一致"

def test_i_json_guard_rejects_invalid_types():
    """验证 I-JSON 守卫能否正确拒绝不兼容的类型。"""
    invalid_key_sets = [
        {"value": 1.23},  # 禁止 float
        {"value": float("nan")},
        {"value": float("inf")},
        {123: "value"},  # 禁止非字符串键
    ]
    for keys in invalid_key_sets:
        with pytest.raises(CanonicalizationError):
            generate_uida(keys)
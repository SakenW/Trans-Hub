# packages/server/tests/unit/domain/test_tm.py
"""
对 `domain/tm.py` 中的领域逻辑进行单元测试。
"""
import pytest
from trans_hub.domain import tm

@pytest.mark.parametrize(
    "input_text, expected_output",
    [
        ("Hello world", "Hello world"),
        ("  leading, trailing  ", "leading, trailing"),
        ("Welcome, {user_name}!", "Welcome, {VAR}!"),
        ("Error ID: a1b2c3d4-e5f6-7890-1234-567890abcdef", "Error ID: {UUID}"),
        ("Visit us at https://example.com/page?q=1", "Visit us at {URL}"),
        ("You have 5 messages and 1,234.56 points.", "You have {NUM} messages and {NUM} points."),
        (123, "123"), (None, "None"),
    ]
)
def test_normalize_text_for_tm(input_text, expected_output):
    """测试 TM 文本归一化函数的正确性。"""
    assert tm.normalize_text_for_tm(input_text) == expected_output

def test_build_reuse_key_stability_and_sensitivity():
    """验证复用键哈希的稳定性和敏感性。"""
    ns = "game.items.v1"
    keys = {"item_id": 123}
    source = {"text": "Diamond Sword"}

    hash1 = tm.build_reuse_key(namespace=ns, reduced_keys=keys, source_fields=source)
    hash2 = tm.build_reuse_key(namespace=ns, reduced_keys=keys, source_fields=source)
    assert hash1 == hash2, "相同的输入必须产生相同的哈希"

    hash_diff_ns = tm.build_reuse_key(namespace="game.items.v2", reduced_keys=keys, source_fields=source)
    hash_diff_keys = tm.build_reuse_key(namespace=ns, reduced_keys={"item_id": 456}, source_fields=source)
    hash_diff_source = tm.build_reuse_key(namespace=ns, reduced_keys=keys, source_fields={"text": "Iron Sword"})
    
    assert hash1 != hash_diff_ns
    assert hash1 != hash_diff_keys
    assert hash1 != hash_diff_source
# tests/unit/test_utils.py
"""针对 `trans_hub.utils` 模块的单元测试。"""

import pytest

from trans_hub.types import GLOBAL_CONTEXT_SENTINEL
from trans_hub.utils import get_context_hash, validate_lang_codes


def test_get_context_hash_stability() -> None:
    """测试 get_context_hash 对相同但顺序不同的字典能生成相同的哈希。"""
    context1 = {"a": 1, "b": "hello"}
    context2 = {"b": "hello", "a": 1}
    assert get_context_hash(context1) == get_context_hash(context2)


def test_get_context_hash_for_empty_or_none() -> None:
    """测试空上下文或 None 会返回全局哨兵值。"""
    assert get_context_hash(None) == GLOBAL_CONTEXT_SENTINEL
    assert get_context_hash({}) == GLOBAL_CONTEXT_SENTINEL


def test_get_context_hash_with_nested_dict() -> None:
    """测试对嵌套字典的哈希稳定性。"""
    context1 = {"a": 1, "b": {"c": 3, "d": 4}}
    context2 = {"a": 1, "b": {"d": 4, "c": 3}}
    assert get_context_hash(context1) == get_context_hash(context2)


def test_validate_lang_codes_valid() -> None:
    """测试有效的语言代码能通过校验。"""
    validate_lang_codes(["en", "zh-CN", "fr", "es-419"])  # Should not raise
    validate_lang_codes(["de"])  # Should not raise


@pytest.mark.parametrize(
    "invalid_code", ["EN", "zh_cn", "german", "e", "en-cn", "en-USA"]
)
def test_validate_lang_codes_invalid(invalid_code: str) -> None:
    """测试无效的语言代码会引发 ValueError。"""
    with pytest.raises(ValueError, match=f"'{invalid_code}' 格式无效"):
        validate_lang_codes([invalid_code])
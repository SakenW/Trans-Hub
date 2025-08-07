# tests/unit/test_utils.py
"""针对 `trans_hub.utils` 模块的单元测试。"""

import pytest

from trans_hub.core.types import GLOBAL_CONTEXT_SENTINEL
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


@pytest.mark.parametrize(
    "valid_codes",
    [
        ["en"],
        ["zh-CN"],
        ["de", "fr", "es-419"],
        ["en-US"],
        # 测试 langcodes 的标准化能力（这些都是可接受的输入）
        ["EN"],
        ["en-gb"],
        ["en_GB"],
        ["fr-CA"],
        ["zh-Hant"],
        # langcodes 将其视为有效
        ["en-Toolong"],
    ],
)
def test_validate_lang_codes_accepts_valid_and_normalizable_tags(
    valid_codes: list[str],
) -> None:
    """测试有效的和可标准化的语言代码都能通过校验，不引发异常。"""
    try:
        validate_lang_codes(valid_codes)
    except ValueError as e:
        pytest.fail(
            f"validate_lang_codes() 错误地对有效代码 {valid_codes} 引发了异常: {e}"
        )


@pytest.mark.parametrize(
    "invalid_code, expected_error_part",
    [
        ("german", "Expected a language code, got 'german'"),
        ("e", "does not conform to the expected format"),
        ("123", "does not contain a language subtag"),
        ("a-DE", "does not conform to the expected format"),
        ("zh-CN-", "Expected 1-8 alphanumeric characters, got ''"),
    ],
)
def test_validate_lang_codes_rejects_invalid_tags(
    invalid_code: str, expected_error_part: str
) -> None:
    """测试真正无效的语言代码会引发 ValueError，并检查错误信息。"""
    with pytest.raises(ValueError) as excinfo:
        validate_lang_codes([invalid_code])

    # 验证我们自己的中文包装错误信息存在
    assert f"提供的语言代码 '{invalid_code}' 格式无效" in str(excinfo.value)
    # 验证来自底层 langcodes 库的英文原因也存在
    assert expected_error_part in str(excinfo.value)

# tests/unit/_tm/test_normalizers.py
# [v2.4] 文本归一化单元测试
"""测试用于翻译记忆库 (TM) 的文本归一化逻辑。"""

from __future__ import annotations

import pytest

from trans_hub._tm.normalizers import normalize_plain_text_for_reuse


@pytest.mark.parametrize(
    "input_text, expected_output",
    [
        ("Hello world", "Hello world"),
        ("AT&amp;T", "AT&T"),
        (
            "  leading, trailing  ,  multiple   spaces  ",
            "leading, trailing , multiple spaces",
        ),
        ('<a href="/home" class="btn">Click <b>me</b></a>', "<a>Click <b>me</b></a>"),
        ("Welcome, {user_name}!", "Welcome, {VAR}!"),
        ("Error ID: a1b2c3d4-e5f6-7890-1234-567890abcdef", "Error ID: {UUID}"),
        ("Visit us at https://example.com/page?q=1", "Visit us at {URL}"),
        (
            "You have 5 messages and 1,234.56 points.",
            "You have {NUM} messages and {NUM} points.",
        ),
        (
            "  Please click &lt;a href='#'&gt;here&lt;/a&gt; to resolve issue {issue_id}. Amount is 100.00.   ",
            "Please click <a>here</a> to resolve issue {VAR}. Amount is {NUM}.",
        ),
        (123, "123"),
        (None, "None"),
    ],
)
def test_normalization_scenarios(input_text, expected_output):
    """使用一组丰富的场景来验证文本归一化函数的正确性。"""
    assert normalize_plain_text_for_reuse(input_text) == expected_output

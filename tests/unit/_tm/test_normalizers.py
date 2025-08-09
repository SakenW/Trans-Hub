# tests/unit/_tm/test_normalizers.py
"""测试用于翻译记忆库 (TM) 的文本归一化逻辑。"""
from __future__ import annotations

import pytest

from trans_hub._tm.normalizers import normalize_plain_text_for_reuse


@pytest.mark.parametrize(
    "input_text, expected_output",
    [
        # 基本情况
        ("Hello world", "Hello world"),
        # HTML 实体
        ("AT&amp;T", "AT&T"),
        # 多余空格
        ("  leading, trailing  ,  multiple   spaces  ", "leading, trailing , multiple spaces"),
        # HTML 标签
        ('<a href="/home" class="btn">Click <b>me</b></a>', "<a>Click <b>me</b></a>"),
        # 占位符
        ("Welcome, {user_name}!", "Welcome, {VAR}!"),
        # UUID
        ("Error ID: a1b2c3d4-e5f6-7890-1234-567890abcdef", "Error ID: {UUID}"),
        # URL
        ("Visit us at https://example.com/page?q=1", "Visit us at {URL}"),
        # 数字
        ("You have 5 messages and 1,234.56 points.", "You have {NUM} messages and {NUM} points."),
        # 混合复杂场景
        (
            "  Please click &lt;a href='#'&gt;here&lt;/a&gt; to resolve issue {issue_id}. Amount is 100.00.   ",
            "Please click <a>here</a> to resolve issue {VAR}. Amount is {NUM}."
        ),
        # 非字符串输入
        (123, "123"),
        (None, "None"),
    ],
)
def test_normalization_scenarios(input_text, expected_output):
    """
    使用一组丰富的场景来验证文本归一化函数的正确性。
    """
    assert normalize_plain_text_for_reuse(input_text) == expected_output
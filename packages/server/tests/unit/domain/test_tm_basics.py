# packages/server/tests/unit/domain/test_tm_basics.py
"""
测试用于翻译记忆库 (TM) 的文本归一化领域逻辑。
(文件已从 uida 包移动并重命名)
"""

import pytest

from trans_hub.domain.tm import normalize_text_for_tm


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
    assert normalize_text_for_tm(input_text) == expected_output

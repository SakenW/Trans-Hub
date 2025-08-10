# packages/server/tests/unit/domain/test_tm.py
"""
对 `domain/tm.py` 中的领域逻辑进行单元测试。
"""
import pytest
from trans_hub.domain import tm

@pytest.mark.parametrize(
    "input_text, expected_output",
    [
        ("Hello, {user_name}!", "Hello, {VAR}!"),
        # ... (其他测试用例与原 `test_tm_basics.py` 一致) ...
    ],
)
def test_normalize_text_for_tm(input_text, expected_output):
    """测试 TM 文本归一化函数的正确性。"""
    assert tm.normalize_text_for_tm(input_text) == expected_output
# tests/helpers/factories.py
# [v2.4 Refactor] UIDA 架构的数据工厂。
"""
提供用于创建一致、可预测的测试数据的工厂函数。
这是所有集成测试的数据生成入口，确保了测试用例的简洁性和可维护性。
"""

from __future__ import annotations

import uuid
from typing import Any

# ---- 定义一组全局共享的、可预测的常量 ----
TEST_PROJECT_ID = "test-project-01"
TEST_NAMESPACE = "test.ui.buttons.v1"
TEST_SOURCE_LANG = "en"
TEST_TARGET_LANG = "de"


def create_uida_request_data(
    *,  # 强制使用关键字参数，提高可读性
    project_id: str = TEST_PROJECT_ID,
    namespace: str = TEST_NAMESPACE,
    keys: dict[str, Any] | None = None,
    source_payload: dict[str, Any] | None = None,
    source_lang: str = TEST_SOURCE_LANG,
    target_langs: list[str] | None = None,
    content_version: int = 1,
    variant_key: str = "-",
) -> dict[str, Any]:
    """
    创建一个标准的、可覆盖的 UIDA 请求字典。
    这使得测试用例可以只关注于它们关心的特定参数变化。

    默认情况下，`keys` 和 `source_payload` 会包含一个唯一 ID，以确保
    每次调用都会生成一个新的、唯一的 content item，避免测试间的状态污染。

    Returns:
        一个完整的字典，可以直接用于 `coordinator.request` 方法。

    """
    # 提供一个合理的、默认唯一的 keys 字典
    unique_id = uuid.uuid4().hex[:8]
    final_keys = {"view": f"view_{unique_id}", "id": f"id_{unique_id}"}
    if keys is not None:
        final_keys = keys  # 如果提供了 keys，则完全替换

    # 提供一个合理的、默认唯一的 source_payload 字典
    final_source_payload = {"text": f"Sample text {unique_id}"}
    if source_payload is not None:
        final_source_payload = source_payload  # 如果提供了 payload，则完全替换

    return {
        "project_id": project_id,
        "namespace": namespace,
        "keys": final_keys,
        "source_payload": final_source_payload,
        "source_lang": source_lang,
        "target_langs": target_langs or [TEST_TARGET_LANG],
        "content_version": content_version,
        "variant_key": variant_key,
    }

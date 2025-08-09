# tests/helpers/factories.py
"""
提供用于创建一致、可预测的测试数据的工厂函数。
这是所有集成测试的数据生成入口。
"""
from __future__ import annotations

import uuid
from typing import Any

# ---- 定义一组全局共享的、可预测的常量 ----
TEST_PROJECT_ID = "prj-a1b2c3d4-e5f6-7890-1234-567890abcdef"
TEST_NAMESPACE = "test.ui.buttons.v1"
TEST_SOURCE_LANG = "en"
TEST_TARGET_LANG = "de"


def create_uida_request_data(
    *, # 强制使用关键字参数，提高可读性
    project_id: str = TEST_PROJECT_ID,
    namespace: str = TEST_NAMESPACE,
    keys: dict[str, Any] | None = None,
    source_payload: dict[str, Any] | None = None,
    source_lang: str = TEST_SOURCE_LANG,
    target_langs: list[str] | None = None,
    content_version: int = 1,
    variant_key: str = '-',
) -> dict[str, Any]:
    """
    创建一个标准的、可覆盖的 UIDA 请求字典。
    这使得测试用例可以只关注于它们关心的特定参数变化。

    Returns:
        一个完整的字典，可以直接用于 `coordinator.request` 方法。
    """
    # 提供一个合理的默认 keys 字典
    final_keys = {"view": f"view_{uuid.uuid4().hex[:6]}", "id": f"id_{uuid.uuid4().hex[:6]}"}
    if keys is not None:
        final_keys.update(keys)

    # 提供一个合理的默认 source_payload 字典
    final_source_payload = {"text": f"Sample text {uuid.uuid4().hex[:6]}"}
    if source_payload is not None:
        final_source_payload.update(source_payload)

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
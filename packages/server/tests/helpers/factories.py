# packages/server/tests/helpers/factories.py
"""
提供用于创建一致、可预测的测试数据的工厂函数。
"""
import uuid
from typing import Any

TEST_PROJECT_ID = "test-project"
TEST_NAMESPACE = "test.namespace.v1"
TEST_SOURCE_LANG = "en"
TEST_TARGET_LANG = "de"

def create_request_data(
    project_id: str = TEST_PROJECT_ID,
    namespace: str = TEST_NAMESPACE,
    keys: dict | None = None,
    source_payload: dict | None = None,
    target_langs: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """创建一个标准的、可覆盖的翻译请求字典。"""
    unique_part = uuid.uuid4().hex[:6]
    final_keys = keys or {"id": f"key-{unique_part}"}
    final_payload = source_payload or {"text": f"Source text {unique_part}"}
    final_targets = target_langs or [TEST_TARGET_LANG]
    
    return {
        "project_id": project_id,
        "namespace": namespace,
        "keys": final_keys,
        "source_payload": final_payload,
        "target_langs": final_targets,
        "source_lang": TEST_SOURCE_LANG,
        **kwargs,
    }
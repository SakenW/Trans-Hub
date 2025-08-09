# tests/unit/_uida/test_reuse_key.py
# [v2.4] 复用键生成单元测试
"""测试复用键的生成逻辑和策略应用。"""
from __future__ import annotations

import pytest

from trans_hub._uida.reuse_key import build_reuse_sha256, reduce_keys_for_reuse


@pytest.fixture
def sample_keys() -> dict[str, str]:
    """提供一个包含版本号的样本 keys。"""
    return {"mod_id": "testmod", "item": "sword", "version": "1.20.1"}


@pytest.fixture
def sample_source_fields() -> dict[str, str]:
    """提供一个样本源文本字段。"""
    return {"text": "Diamond Sword"}


def test_reduce_keys_ignore_fields(sample_keys):
    """测试 `ignore_fields` 策略能否正确移除字段。"""
    policy = {"ignore_fields": ["version"]}
    reduced = reduce_keys_for_reuse(sample_keys, policy)
    assert "version" not in reduced
    assert "mod_id" in reduced
    assert reduced == {"mod_id": "testmod", "item": "sword"}


def test_build_reuse_sha256_is_stable_and_sensitive(sample_source_fields):
    """验证复用键哈希的稳定性和敏感性。"""
    ns = "game.items.v1"
    keys = {"item_id": 123}

    # 相同的输入必须产生相同的哈希
    hash1 = build_reuse_sha256(
        namespace=ns, reduced_keys=keys, source_fields=sample_source_fields
    )
    hash2 = build_reuse_sha256(
        namespace=ns, reduced_keys=keys, source_fields=sample_source_fields
    )
    assert hash1 == hash2

    # 任何输入的变化都必须产生不同的哈希
    hash_diff_ns = build_reuse_sha256(
        namespace="game.items.v2", reduced_keys=keys, source_fields=sample_source_fields
    )
    hash_diff_keys = build_reuse_sha256(
        namespace=ns, reduced_keys={"item_id": 456}, source_fields=sample_source_fields
    )
    hash_diff_source = build_reuse_sha256(
        namespace=ns, reduced_keys=keys, source_fields={"text": "Iron Sword"}
    )

    assert hash1 != hash_diff_ns
    assert hash1 != hash_diff_keys
    assert hash1 != hash_diff_source
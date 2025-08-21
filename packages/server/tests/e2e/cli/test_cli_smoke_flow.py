# tests/e2e/cli/test_cli_smoke_flow.py
"""
对 CLI 进行端到端的冒烟测试，覆盖完整的生命周期 (v3.2.3 最终凭证修复版)。
"""

import json
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from unittest.mock import MagicMock

from tests.helpers.factories import create_request_data
from trans_hub.presentation.cli.commands import request as request_cmd
from trans_hub.presentation.cli.commands import status as status_cmd
from trans_hub.presentation.cli._state import CLISharedState
from trans_hub_core.types import TranslationStatus
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.uow import UowFactory


@pytest_asyncio.fixture
async def mock_cli_context(
    test_config: TransHubConfig,
    migrated_db: AsyncEngine,
) -> AsyncGenerator[MagicMock, None]:
    """
    [最终修复] 创建一个模拟的 Typer Context。
    它克隆一份配置，然后注入临时数据库的、包含真实凭证的 URL。
    """
    local_config = test_config.model_copy(deep=True)

    # [关键修复] 必须使用 render_as_string(hide_password=False) 获取包含密码的 DSN
    real_db_url_with_creds = migrated_db.url.render_as_string(hide_password=False)
    local_config.database.url = real_db_url_with_creds

    mock = MagicMock()
    mock.obj = CLISharedState(config=local_config)

    yield mock


@pytest.mark.asyncio
async def test_cli_full_lifecycle_flow(
    uow_factory: UowFactory,
    mock_cli_context: MagicMock,
    capsys,
):
    """
    测试通过 CLI 驱动的 "Request -> Publish -> Unpublish -> Reject -> Comment" 完整闭环。
    """
    # === 阶段 1: 通过 CLI 提交请求 ===
    req_data = create_request_data(
        target_langs=["ja"], keys={"id": f"cli-e2e-full-{uuid.uuid4().hex[:6]}"}
    )
    await request_cmd.request_new(
        ctx=mock_cli_context,
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys_json=json.dumps(req_data["keys"]),
        source_payload_json=json.dumps(req_data["source_payload"]),
        target_langs=["ja"],
    )
    assert "翻译请求已成功提交" in capsys.readouterr().out

    # === 阶段 2: 准备 'reviewed' 修订 (直接使用 uow_factory) ===
    async with uow_factory() as uow:
        head = await uow.translations.get_head_by_uida(
            project_id=req_data["project_id"],
            namespace=req_data["namespace"],
            keys=req_data["keys"],
            target_lang="ja",
            variant_key="-",
        )
        assert head is not None
        head_id = head.id
        content_id = head.content_id

        rev_id = await uow.translations.create_revision(
            head_id=head.id,
            project_id=head.project_id,
            content_id=content_id,
            target_lang="ja",
            variant_key="-",
            status=TranslationStatus.REVIEWED,
            revision_no=head.current_no + 1,
            translated_payload_json={"text": "こんにちは世界"},
        )

    # === 阶段 3: 通过 CLI 管理生命周期 ===
    await status_cmd.publish(ctx=mock_cli_context, revision_id=rev_id)
    assert "已成功发布" in capsys.readouterr().out

    await status_cmd.unpublish(ctx=mock_cli_context, revision_id=rev_id)
    assert "发布已被撤回" in capsys.readouterr().out

    await status_cmd.reject(ctx=mock_cli_context, revision_id=rev_id)
    assert "已被标记为 'rejected'" in capsys.readouterr().out

    # === 阶段 4: 通过 CLI 评论 ===
    comment_author = "cli-test-user"
    comment_body = "This is an E2E test comment."
    await status_cmd.add_comment(
        ctx=mock_cli_context, head_id=head_id, body=comment_body, author=comment_author
    )
    assert "评论已添加" in capsys.readouterr().out

    await status_cmd.get_comments(ctx=mock_cli_context, head_id=head_id)
    captured = capsys.readouterr()
    assert comment_author in captured.out
    assert comment_body in captured.out

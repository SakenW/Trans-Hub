# packages/server/tests/integration/management/test_db_service.py
from unittest.mock import patch

import pytest
from sqlalchemy import Engine, text
from tests.helpers.tools.db_manager import _alembic_ini
from trans_hub.config import TransHubConfig
from trans_hub.management.db_service import DbService

pytestmark = [pytest.mark.db, pytest.mark.integration]


@pytest.fixture
def db_service(test_config: TransHubConfig) -> DbService:
    """提供一个连接到测试配置的 DbService 实例。"""
    return DbService(config=test_config, alembic_ini_path=str(_alembic_ini()))


def test_db_service_check_status_success(
    db_service: DbService, sync_migrated_db: Engine
):
    """测试健康检查在数据库已成功迁移时的行为。"""
    db_service.config.database.url = sync_migrated_db.url.render_as_string(
        hide_password=False
    )
    # check_status 内部会创建自己的引擎，所以我们只需确保 URL 是正确的
    assert db_service.check_status() is True


def test_db_service_rebuild_database(db_service: DbService, sync_migrated_db: Engine):
    """测试数据库重建流程是否能被调用。"""
    db_service.config.database.url = sync_migrated_db.url.render_as_string(
        hide_password=False
    )
    maint_url = sync_migrated_db.url.set(database="postgres")
    db_service.sync_maint_url = maint_url

    # 我们只测试 DbService 是否正确调用了 alembic，而不测试 alembic 本身
    with (
        patch("alembic.command.upgrade") as mock_upgrade,
        patch("alembic.command.downgrade") as mock_downgrade,
    ):
        db_service.rebuild_database()
        mock_downgrade.assert_called_once_with(db_service.alembic_cfg, "base")
        mock_upgrade.assert_called_once_with(db_service.alembic_cfg, "head")

    # 验证重建后，版本表依然存在且有记录
    with sync_migrated_db.connect() as conn:
        result = conn.execute(
            text("SELECT version_num FROM th.alembic_version")
        ).scalar_one_or_none()
        assert result is not None

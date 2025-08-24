# packages/server/tests/unit/management/test_config_utils.py
"""
配置工具模块的单元测试。
"""

from __future__ import annotations

import pytest
from sqlalchemy.engine.url import make_url
from unittest.mock import patch, MagicMock

from trans_hub.management.config_utils import (
    mask_db_url,
    get_real_db_url,
    convert_async_to_sync_url,
    validate_database_connection,
)


class TestMaskDbUrl:
    """测试数据库 URL 脱敏功能。"""

    def test_mask_postgresql_url(self):
        """测试 PostgreSQL URL 脱敏。"""
        url = "postgresql+asyncpg://user:secret123@localhost:5432/testdb"
        masked = mask_db_url(url)
        assert "secret123" not in masked
        assert "***" in masked
        assert "user" in masked
        assert "localhost" in masked
        assert "testdb" in masked

    def test_mask_sqlite_url(self):
        """测试 SQLite URL 脱敏。"""
        url = "sqlite+aiosqlite:///path/to/db.sqlite"
        masked = mask_db_url(url)
        # SQLite URL 通常没有密码，应该保持原样
        assert "sqlite+aiosqlite" in masked
        assert "path/to/db.sqlite" in masked

    def test_mask_none_url(self):
        """测试 None URL 处理。"""
        masked = mask_db_url(None)
        assert masked == "[未配置]"

    def test_mask_invalid_url(self):
        """测试无效 URL 处理。"""
        masked = mask_db_url("invalid-url")
        assert masked == "[无法解析的数据库 URL]"

    def test_mask_url_object(self):
        """测试 URL 对象脱敏。"""
        url_obj = make_url("postgresql://user:password@host/db")
        masked = mask_db_url(url_obj)
        assert "password" not in masked
        assert "***" in masked


class TestGetRealDbUrl:
    """测试获取真实数据库 URL 功能。"""

    def test_get_real_url_string(self):
        """测试从字符串获取真实 URL。"""
        url = "postgresql+asyncpg://user:secret123@localhost:5432/testdb"
        real_url = get_real_db_url(url)
        assert "secret123" in real_url
        assert real_url == url

    def test_get_real_url_object(self):
        """测试从 URL 对象获取真实 URL。"""
        url_obj = make_url("postgresql://user:password@host/db")
        real_url = get_real_db_url(url_obj)
        assert "password" in real_url
        assert "postgresql://user:password@host/db" == real_url


class TestConvertAsyncToSyncUrl:
    """测试异步 URL 转换为同步 URL 功能。"""

    def test_convert_asyncpg_to_psycopg(self):
        """测试 asyncpg 转换为 psycopg。"""
        async_url = "postgresql+asyncpg://user:pass@host/db"
        sync_url = convert_async_to_sync_url(async_url)
        assert "+asyncpg" not in sync_url
        assert "+psycopg" in sync_url
        assert "user:pass@host/db" in sync_url

    def test_convert_aiosqlite_to_sqlite(self):
        """测试 aiosqlite 转换为 sqlite。"""
        async_url = "sqlite+aiosqlite:///path/to/db.sqlite"
        sync_url = convert_async_to_sync_url(async_url)
        assert "+aiosqlite" not in sync_url
        assert "sqlite:///path/to/db.sqlite" == sync_url

    def test_convert_aiomysql_to_pymysql(self):
        """测试 aiomysql 转换为 pymysql。"""
        async_url = "mysql+aiomysql://user:pass@host/db"
        sync_url = convert_async_to_sync_url(async_url)
        assert "+aiomysql" not in sync_url
        assert "+pymysql" in sync_url

    def test_convert_unknown_driver(self):
        """测试未知驱动保持原样。"""
        async_url = "postgresql://user:pass@host/db"
        sync_url = convert_async_to_sync_url(async_url)
        assert sync_url == async_url

    def test_convert_url_object(self):
        """测试 URL 对象转换。"""
        url_obj = make_url("postgresql+asyncpg://user:pass@host/db")
        sync_url = convert_async_to_sync_url(url_obj)
        assert "+psycopg" in sync_url
        assert "user:pass@host/db" in sync_url


class TestValidateDatabaseConnection:
    """测试数据库连接验证功能。"""

    @patch('trans_hub.management.config_utils.create_engine')
    def test_validate_connection_success(self, mock_create_engine):
        """测试成功的数据库连接验证。"""
        # 模拟成功的数据库连接
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        result = validate_database_connection(
            database_url="postgresql+asyncpg://user:pass@host/db",
            maintenance_url="postgresql://admin:pass@host/postgres"
        )

        assert result is True
        # 验证创建了两个引擎（维护库和主库）
        assert mock_create_engine.call_count == 2
        # 验证执行了 SELECT 1 查询
        assert mock_conn.execute.call_count == 2

    @patch('trans_hub.management.config_utils.create_engine')
    def test_validate_connection_no_maintenance(self, mock_create_engine):
        """测试没有维护库的连接验证。"""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        result = validate_database_connection(
            database_url="postgresql+asyncpg://user:pass@host/db"
        )

        assert result is True
        # 只创建了一个引擎（主库）
        assert mock_create_engine.call_count == 1
        # 只执行了一次 SELECT 1 查询
        assert mock_conn.execute.call_count == 1

    @patch('trans_hub.management.config_utils.create_engine')
    def test_validate_connection_operational_error(self, mock_create_engine):
        """测试数据库连接操作错误。"""
        from sqlalchemy.exc import OperationalError
        
        mock_create_engine.side_effect = OperationalError(
            "connection failed", None, None
        )

        result = validate_database_connection(
            database_url="postgresql+asyncpg://user:pass@host/db"
        )

        assert result is False

    @patch('trans_hub.management.config_utils.create_engine')
    def test_validate_connection_unexpected_error(self, mock_create_engine):
        """测试数据库连接意外错误。"""
        mock_create_engine.side_effect = ValueError("unexpected error")

        result = validate_database_connection(
            database_url="postgresql+asyncpg://user:pass@host/db"
        )

        assert result is False

    @patch('trans_hub.management.config_utils.create_engine')
    def test_validate_connection_custom_type(self, mock_create_engine):
        """测试自定义连接类型描述。"""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        result = validate_database_connection(
            database_url="postgresql+asyncpg://user:pass@host/db",
            connection_type="测试"
        )

        assert result is True
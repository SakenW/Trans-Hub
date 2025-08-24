# packages/server/tests/unit/infrastructure/db/test_utils.py
"""
数据库工具模块的单元测试

测试统一数据库加载处理机制的各个组件，包括：
- 数据库驱动自动识别
- 连接池配置生成
- Schema配置解析
- 数据库信息获取
"""

import pytest
from unittest.mock import Mock
from sqlalchemy.pool import NullPool, QueuePool

from trans_hub.config import TransHubConfig, DatabaseSettings
from trans_hub.infrastructure.db.utils import (
    DatabaseDriver,
    DatabaseConfig,
    detect_database_driver,
    create_optimal_pool_config,
    resolve_database_schema,
    create_database_config,
    get_database_info,
)


class TestDatabaseDriver:
    """测试数据库驱动枚举"""
    
    def test_driver_values(self):
        """测试驱动枚举值"""
        assert DatabaseDriver.SQLITE.value == "sqlite+aiosqlite"
        assert DatabaseDriver.POSTGRESQL.value == "postgresql+asyncpg"
        assert DatabaseDriver.MYSQL.value == "mysql+aiomysql"


class TestDatabaseConfig:
    """测试数据库配置容器"""
    
    def test_sqlite_properties(self):
        """测试SQLite配置属性"""
        config = DatabaseConfig(
            driver=DatabaseDriver.SQLITE,
            url="sqlite+aiosqlite:///test.db",
            schema=None
        )
        
        assert config.is_sqlite is True
        assert config.is_postgresql is False
        assert config.is_mysql is False
        assert config.supports_schema is False
    
    def test_postgresql_properties(self):
        """测试PostgreSQL配置属性"""
        config = DatabaseConfig(
            driver=DatabaseDriver.POSTGRESQL,
            url="postgresql+asyncpg://user:pass@localhost/db",
            schema="th"
        )
        
        assert config.is_sqlite is False
        assert config.is_postgresql is True
        assert config.is_mysql is False
        assert config.supports_schema is True
    
    def test_mysql_properties(self):
        """测试MySQL配置属性"""
        config = DatabaseConfig(
            driver=DatabaseDriver.MYSQL,
            url="mysql+aiomysql://user:pass@localhost/db",
            schema="th"
        )
        
        assert config.is_sqlite is False
        assert config.is_postgresql is False
        assert config.is_mysql is True
        assert config.supports_schema is True


class TestDetectDatabaseDriver:
    """测试数据库驱动检测"""
    
    def test_detect_sqlite_driver(self):
        """测试SQLite驱动检测"""
        urls = [
            "sqlite+aiosqlite:///test.db",
            "sqlite+aiosqlite:////absolute/path/test.db",
            "sqlite:///:memory:",
        ]
        
        for url in urls:
            driver = detect_database_driver(url)
            assert driver == DatabaseDriver.SQLITE
    
    def test_detect_postgresql_driver(self):
        """测试PostgreSQL驱动检测"""
        urls = [
            "postgresql+asyncpg://user:pass@localhost/db",
            "postgresql+asyncpg://user@localhost:5432/db",
            "postgresql://user:pass@localhost/db",  # 简化形式
        ]
        
        for url in urls:
            driver = detect_database_driver(url)
            assert driver == DatabaseDriver.POSTGRESQL
    
    def test_detect_mysql_driver(self):
        """测试MySQL驱动检测"""
        urls = [
            "mysql+aiomysql://user:pass@localhost/db",
            "mysql+aiomysql://user@localhost:3306/db",
            "mysql://user:pass@localhost/db",  # 简化形式
        ]
        
        for url in urls:
            driver = detect_database_driver(url)
            assert driver == DatabaseDriver.MYSQL
    
    def test_unsupported_driver(self):
        """测试不支持的驱动"""
        with pytest.raises(ValueError, match="不支持的数据库驱动"):
            detect_database_driver("oracle://user:pass@localhost/db")
    
    def test_invalid_url(self):
        """测试无效的URL"""
        with pytest.raises(ValueError, match="无法解析数据库URL"):
            detect_database_driver("invalid-url")


class TestCreateOptimalPoolConfig:
    """测试连接池配置生成"""
    
    def test_sqlite_pool_config(self):
        """测试SQLite连接池配置"""
        config = Mock()
        config.db_echo = False
        config.database = Mock()
        config.database.echo = False
        config.db_pool_pre_ping = True
        
        pool_config = create_optimal_pool_config(DatabaseDriver.SQLITE, config)
        
        assert pool_config["poolclass"] == NullPool
        assert pool_config["echo"] is False
        assert pool_config["pool_pre_ping"] is True
        assert pool_config["future"] is True
        
        # SQLite不应该有连接池参数
        assert "pool_size" not in pool_config
        assert "max_overflow" not in pool_config
    
    def test_postgresql_pool_config(self):
        """测试PostgreSQL连接池配置"""
        config = Mock()
        config.db_echo = True
        config.database = Mock()
        config.database.echo = False
        config.db_pool_pre_ping = True
        config.db_pool_size = 15
        config.db_max_overflow = 25
        config.db_pool_recycle = 3600
        config.db_pool_timeout = 30
        
        pool_config = create_optimal_pool_config(DatabaseDriver.POSTGRESQL, config)
        
        assert pool_config["poolclass"] == QueuePool
        assert pool_config["echo"] is True  # db_echo优先
        assert pool_config["pool_pre_ping"] is True
        assert pool_config["future"] is True
        assert pool_config["pool_size"] == 15
        assert pool_config["max_overflow"] == 25
        assert pool_config["pool_recycle"] == 3600
        assert pool_config["pool_timeout"] == 30
    
    def test_mysql_pool_config_defaults(self):
        """测试MySQL连接池配置（使用默认值）"""
        config = Mock()
        config.db_echo = False
        config.database = Mock()
        config.database.echo = False
        config.db_pool_pre_ping = True
        config.db_pool_size = None
        config.db_max_overflow = None
        config.db_pool_recycle = None
        config.db_pool_timeout = 30
        
        pool_config = create_optimal_pool_config(DatabaseDriver.MYSQL, config)
        
        assert pool_config["poolclass"] == QueuePool
        assert pool_config["pool_size"] == 8  # MySQL默认值
        assert pool_config["max_overflow"] == 15  # MySQL默认值
        assert "pool_recycle" not in pool_config  # None值不添加
        assert pool_config["pool_timeout"] == 30


class TestResolveDatabaseSchema:
    """测试数据库Schema解析"""
    
    def test_sqlite_schema_resolution(self):
        """测试SQLite Schema解析"""
        config = Mock()
        config.database = Mock()
        config.database.default_schema = "th"
        
        schema = resolve_database_schema(DatabaseDriver.SQLITE, config)
        assert schema is None  # SQLite不支持schema
    
    def test_postgresql_schema_resolution(self):
        """测试PostgreSQL Schema解析"""
        config = Mock()
        config.database = Mock()
        config.database.default_schema = "th"
        
        schema = resolve_database_schema(DatabaseDriver.POSTGRESQL, config)
        assert schema == "th"
    
    def test_mysql_schema_resolution(self):
        """测试MySQL Schema解析"""
        config = Mock()
        config.database = Mock()
        config.database.default_schema = "th"
        
        schema = resolve_database_schema(DatabaseDriver.MYSQL, config)
        assert schema == "th"


class TestCreateDatabaseConfig:
    """测试统一数据库配置创建"""
    
    def test_create_sqlite_config(self):
        """测试创建SQLite配置"""
        config = TransHubConfig(
            database=DatabaseSettings(
                url="sqlite+aiosqlite:///test.db",
                default_schema="th"
            )
        )
        
        db_config = create_database_config(config)
        
        assert db_config.driver == DatabaseDriver.SQLITE
        assert db_config.url == "sqlite+aiosqlite:///test.db"
        assert db_config.schema is None  # SQLite不支持schema
        assert db_config.pool_config["poolclass"] == NullPool
        assert db_config.is_sqlite is True
        assert db_config.supports_schema is False
    
    def test_create_postgresql_config(self):
        """测试创建PostgreSQL配置"""
        config = TransHubConfig(
            database=DatabaseSettings(
                url="postgresql+asyncpg://user:pass@localhost/db",
                default_schema="th"
            )
        )
        
        db_config = create_database_config(config)
        
        assert db_config.driver == DatabaseDriver.POSTGRESQL
        assert db_config.url == "postgresql+asyncpg://user:pass@localhost/db"
        assert db_config.schema == "th"
        assert db_config.pool_config["poolclass"] == QueuePool
        assert db_config.is_postgresql is True
        assert db_config.supports_schema is True


class TestGetDatabaseInfo:
    """测试数据库信息获取"""
    
    def test_get_sqlite_info(self):
        """测试获取SQLite信息"""
        url = "sqlite+aiosqlite:///test.db"
        info = get_database_info(url)
        
        assert info["driver"] == "sqlite+aiosqlite"
        assert info["database"] == "test.db"
        assert info["host"] is None
        assert info["port"] is None
        assert info["username"] is None
        assert info["supports_schema"] is False
        assert info["is_sqlite"] is True
        assert info["is_postgresql"] is False
        assert info["is_mysql"] is False
    
    def test_get_postgresql_info(self):
        """测试获取PostgreSQL信息"""
        url = "postgresql+asyncpg://testuser:testpass@localhost:5432/testdb"
        info = get_database_info(url)
        
        assert info["driver"] == "postgresql+asyncpg"
        assert info["database"] == "testdb"
        assert info["host"] == "localhost"
        assert info["port"] == 5432
        assert info["username"] == "testuser"
        assert info["supports_schema"] is True
        assert info["is_sqlite"] is False
        assert info["is_postgresql"] is True
        assert info["is_mysql"] is False
    
    def test_get_mysql_info(self):
        """测试获取MySQL信息"""
        url = "mysql+aiomysql://testuser:testpass@localhost:3306/testdb"
        info = get_database_info(url)
        
        assert info["driver"] == "mysql+aiomysql"
        assert info["database"] == "testdb"
        assert info["host"] == "localhost"
        assert info["port"] == 3306
        assert info["username"] == "testuser"
        assert info["supports_schema"] is True
        assert info["is_sqlite"] is False
        assert info["is_postgresql"] is False
        assert info["is_mysql"] is True
    
    def test_get_invalid_url_info(self):
        """测试获取无效URL信息"""
        url = "invalid-url"
        info = get_database_info(url)
        
        assert "error" in info
        assert info["raw_url"] == url
        assert "无法解析数据库URL" in info["error"] or "error" in info
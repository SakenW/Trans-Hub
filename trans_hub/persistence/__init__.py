# trans_hub/persistence/__init__.py
"""本模块作为持久化层的公共入口，导出核心组件。"""

from trans_hub.config import TransHubConfig
from trans_hub.core.exceptions import ConfigurationError
from trans_hub.core.interfaces import PersistenceHandler


def create_persistence_handler(config: TransHubConfig) -> PersistenceHandler:
    """根据配置创建并返回一个具体的持久化处理器实例。"""
    db_url = config.database_url

    # [核心修复] 直接基于 URL scheme 进行判断，与 config.db_path 解耦。
    # 这样更健壮，不依赖于 TransHubConfig 的内部实现细节。
    if db_url.startswith("sqlite"):
        from .sqlite import SQLitePersistenceHandler

        # SQLite Handler 仍然需要文件路径，但我们从 config.db_path 获取，
        # 这个属性已经过验证和清理。
        return SQLitePersistenceHandler(db_path=config.db_path)
    elif db_url.startswith("postgresql"):
        try:
            from .postgres import PostgresPersistenceHandler

            return PostgresPersistenceHandler(dsn=db_url)
        except ImportError as e:
            raise ConfigurationError(
                "要使用 PostgreSQL, 请安装 'asyncpg' 驱动: "
                '"pip install "trans-hub[postgres]"'
            ) from e
    else:
        raise ConfigurationError(f"不支持的数据库类型或驱动: '{db_url}'")


from .sqlite import SQLitePersistenceHandler as DefaultPersistenceHandler

__all__ = [
    "create_persistence_handler",
    "DefaultPersistenceHandler",
    "PersistenceHandler",
]

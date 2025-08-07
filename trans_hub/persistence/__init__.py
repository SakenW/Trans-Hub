# trans_hub/persistence/__init__.py
"""本模块作为持久化层的公共入口，导出核心组件。"""

from trans_hub.config import TransHubConfig
from trans_hub.core.exceptions import ConfigurationError
from trans_hub.core.interfaces import PersistenceHandler


def create_persistence_handler(config: TransHubConfig) -> PersistenceHandler:
    """根据配置创建并返回一个具体的持久化处理器实例。"""
    db_url = config.database_url

    # --- [核心修复] 检查 scheme 是否以 'sqlite' 开头 ---
    if db_url.startswith("sqlite"):
        from .sqlite import SQLitePersistenceHandler
        # [核心修复] 向 SQLitePersistenceHandler 传递纯净的文件路径
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
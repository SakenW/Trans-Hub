# packages/server/src/trans_hub/infrastructure/db/base.py
"""
定义了 SQLAlchemy 的元数据 (MetaData) 和声明式基类 (DeclarativeBase)。

此模块的核心思想是导出一个单一的 `metadata` 实例，该实例的 `schema` 属性
可以在运行时由引擎工厂根据配置动态设置。

所有 ORM 模型都将通过 `Base` 类与这个单一的 `metadata` 实例关联。
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

# 导出一个可在运行时配置的、单一的 MetaData 实例。
metadata = MetaData()


class Base(MappedAsDataclass, DeclarativeBase):
    """
    项目统一的声明式基类。

    它被配置为数据类 (`MappedAsDataclass`)，并与模块级的 `metadata` 实例关联。
    """

    __abstract__ = True
    metadata = metadata
    pass

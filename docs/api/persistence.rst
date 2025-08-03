.. # docs/api/persistence.rst

=========================
持久化层 (Persistence)
=========================

本部分文档详细介绍了 `Trans-Hub` 的持久化层。持久化层负责所有与数据存储相关的操作，是系统的基石之一。

设计哲学
--------

所有 `PersistenceHandler` 的实现都应遵循以下核心原则：

- **纯异步**: `PersistenceHandler` 是一个**纯异步**的接口。所有的方法都必须是 `async def`，并且不能执行任何阻塞 I/O 操作。

- **事务性**: 所有改变数据库状态的写操作（如创建任务、保存结果）都应该是**原子性**的，以保证数据的一致性。

- **并发安全**: `PersistenceHandler` 的实现**必须**保证其所有公共方法都是并发安全的。对于像 SQLite 这样不支持并发写事务的后端，实现者**必须**在内部使用锁或其他机制来串行化写操作。

- **职责单一**: `PersistenceHandler` 的实现只负责与数据库的直接交互。它不应该包含任何业务逻辑（如重试、缓存查找），这些都由 `Coordinator` 负责。

持久化接口协议
----------------

`PersistenceHandler` 是 `Trans-Hub` 中所有数据持久化操作的**抽象接口协议** (`typing.Protocol`)。任何希望为 `Trans-Hub` 提供自定义存储后端（例如 PostgreSQL, MySQL）的开发者，都必须实现这个协议中定义的所有异步方法。

.. currentmodule:: trans_hub.interfaces

.. autoclass:: PersistenceHandler
   :members:
   :undoc-members: false
   :show-inheritance:

   .. rubric:: 核心方法详解

   .. automethod:: ensure_pending_translations
      :no-index:

      此方法是 `Coordinator.request()` 调用的核心。一个健壮的实现必须在一个**单一的原子事务**中完成所有关联的数据库检查和写入操作，以确保数据的一致性。

   .. automethod:: stream_translatable_items
      :no-index:


默认 SQLite 实现
-----------------

.. currentmodule:: trans_hub.persistence.sqlite

`SQLitePersistenceHandler` 是 `PersistenceHandler` 协议的默认实现，它使用 `aiosqlite` 库来与 SQLite 数据库进行异步交互。

.. autoclass:: SQLitePersistenceHandler
   :members: __init__
   :undoc-members: false
   :show-inheritance:

持久化层工厂函数
------------------

.. currentmodule:: trans_hub.persistence

.. autofunction:: create_persistence_handler

   这是一个便捷的工厂函数，它会根据传入的 `TransHubConfig` 中的 `database_url` 来决定实例化并返回哪一个 `PersistenceHandler` 的具体实现。
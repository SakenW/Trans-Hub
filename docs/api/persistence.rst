.. # docs/api/persistence.rst

持久化层 (Persistence)
========================

本部分定义了持久化层的接口协议，并展示了默认的 SQLite 实现。

持久化接口
----------
.. automodule:: trans_hub.interfaces
   :members: PersistenceHandler
   :undoc-members: false

SQLite 实现
-----------
.. automodule:: trans_hub.persistence.sqlite
   :members: SQLitePersistenceHandler
   :undoc-members: false
   :show-inheritance:

工厂函数
--------
.. automodule:: trans_hub.persistence
   :members: create_persistence_handler
   :undoc-members: false
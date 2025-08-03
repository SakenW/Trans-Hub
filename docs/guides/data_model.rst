.. # docs/guides/data_model.rst

=========================
数据库模型与 Schema 规范
=========================

:目标读者: 核心维护者、数据库管理员，以及需要直接与数据库交互或理解数据持久化逻辑的开发者。
:文档目的: 本文档是 `Trans-Hub` 项目数据模型和数据库 Schema 的权威规范。它详尽地描述了每个表的结构、字段含义、索引和设计决策。

数据库要求
----------

- **默认实现**: **SQLite**。为保证高并发性能，**必须以 WAL (Write-Ahead Logging) 模式运行**。
- **原子性要求**: `PersistenceHandler` 的所有写操作**必须是事务性原子操作**。
- **数据库迁移**: 迁移通过独立的 `schema_manager.py` 和 SQL 文件进行管理，是部署和应用启动时的必要步骤。

.. code-block:: sql
   :caption: 数据库基本设置 (来自 001_initial.sql)

   PRAGMA foreign_keys = ON;
   PRAGMA journal_mode = WAL;

数据实体关系图 (ERD)
--------------------

.. mermaid::

   erDiagram
       th_content {
           TEXT id PK
           TEXT value UNIQUE
       }
       th_contexts {
           TEXT id PK
           TEXT context_hash UNIQUE
           TEXT value
       }
       th_jobs {
           TEXT id PK
           TEXT business_id
           TEXT content_id FK
           TEXT context_id FK
           TIMESTAMP last_requested_at
       }
       th_translations {
           TEXT id PK
           TEXT content_id FK
           TEXT context_id FK
           TEXT lang_code
           TEXT status
       }
       th_content ||--o{ th_jobs : "关联"
       th_contexts ||--o{ th_jobs : "关联"
       th_content ||--o{ th_translations : "包含"
       th_contexts ||--o{ th_translations : "包含"


Schema 详解
-----------

元数据表 (`th_meta`)
^^^^^^^^^^^^^^^^^^^^^

- **职责**: 存储数据库自身的元数据，最重要的就是 Schema 版本号。
- **实现**:

.. code-block:: sql

   CREATE TABLE IF NOT EXISTS th_meta (
       key TEXT PRIMARY KEY NOT NULL,
       value TEXT NOT NULL
   );
   INSERT OR IGNORE INTO th_meta (key, value) VALUES ('schema_version', '1');

内容表 (`th_content`)
^^^^^^^^^^^^^^^^^^^^^

- **职责**: 存储所有唯一的、去重后的文本字符串。这是所有翻译的“单一事实来源”。
- **实现**:

.. code-block:: sql

   CREATE TABLE IF NOT EXISTS th_content (
       id TEXT PRIMARY KEY,
       value TEXT NOT NULL UNIQUE
   );

上下文表 (`th_contexts`)
===========================

- **职责**: 存储唯一的上下文信息及其哈希值。
- **实现**:

.. code-block:: sql

   CREATE TABLE IF NOT EXISTS th_contexts (
       id TEXT PRIMARY KEY,
       context_hash TEXT NOT NULL UNIQUE,
       value TEXT NOT NULL
   );

任务/请求表 (`th_jobs`)
^^^^^^^^^^^^^^^^^^^^^^^^^

- **职责**: 建立业务逻辑标识符 (`business_id`) 与具体内容 (`content_id`) 和上下文 (`context_id`) 之间的权威关联。
- **实现**:

.. code-block:: sql

   CREATE TABLE IF NOT EXISTS th_jobs (
       id TEXT PRIMARY KEY,
       business_id TEXT NOT NULL,
       content_id TEXT NOT NULL,
       context_id TEXT,
       last_requested_at TIMESTAMP NOT NULL,
       FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE,
       FOREIGN KEY(context_id) REFERENCES th_contexts(id) ON DELETE SET NULL
   );

译文表 (`th_translations`)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- **职责**: 存储一个内容针对特定语言和上下文的翻译结果及其生命周期状态。
- **实现**:

.. code-block:: sql

   CREATE TABLE IF NOT EXISTS th_translations (
       id TEXT PRIMARY KEY,
       content_id TEXT NOT NULL,
       context_id TEXT,
       lang_code TEXT NOT NULL,
       source_lang_code TEXT,
       translation_content TEXT,
       engine TEXT,
       engine_version TEXT,
       score REAL,
       status TEXT NOT NULL CHECK(status IN ('PENDING', 'TRANSLATING', 'TRANSLATED', 'FAILED', 'APPROVED')),
       error TEXT,
       last_updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
       FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE,
       FOREIGN KEY(context_id) REFERENCES th_contexts(id) ON DELETE SET NULL
   );


死信队列 (`th_dead_letter_queue`)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- **职责**: 存放经过多次重试后依然失败、无法处理的任务，以便进行人工排查。
- **实现**:

.. code-block:: sql

    CREATE TABLE IF NOT EXISTS th_dead_letter_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_content TEXT NOT NULL,
        source_lang_code TEXT,
        target_lang_code TEXT NOT NULL,
        context_hash TEXT,
        context_json TEXT,
        engine_name TEXT,
        engine_version TEXT,
        last_error_message TEXT NOT NULL,
        failed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

索引与约束
----------

- **性能索引**: 为了提升查询性能，我们为常用查询字段建立了标准索引。

.. code-block:: sql

   CREATE INDEX IF NOT EXISTS idx_jobs_last_requested_at ON th_jobs(last_requested_at);
   CREATE INDEX IF NOT EXISTS idx_translations_status_lang ON th_translations(status, lang_code);
   CREATE INDEX IF NOT EXISTS idx_dlq_failed_at ON th_dead_letter_queue(failed_at);

- **唯一性约束 (关键设计)**: 标准的 `UNIQUE` 复合约束在处理 `NULL` 值时存在缺陷。为了确保 `(business_id, content_id, context_id)` 和 `(content_id, lang_code, context_id)` 的组合在 `context_id` 为 `NULL` 时依然能保证唯一性，我们使用了 **部分唯一索引 (Partial Unique Indexes)**。

.. code-block:: sql
   :caption: Jobs 表的唯一性约束

   CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_unique_with_context
   ON th_jobs(business_id, content_id, context_id)
   WHERE context_id IS NOT NULL;

   CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_unique_without_context
   ON th_jobs(business_id, content_id)
   WHERE context_id IS NULL;

.. code-block:: sql
   :caption: Translations 表的唯一性约束

   CREATE UNIQUE INDEX IF NOT EXISTS idx_translations_unique_with_context
   ON th_translations(content_id, lang_code, context_id)
   WHERE context_id IS NOT NULL;

   CREATE UNIQUE INDEX IF NOT EXISTS idx_translations_unique_without_context
   ON th_translations(content_id, lang_code)
   WHERE context_id IS NULL;

垃圾回收 (GC)
-------------

`Coordinator.run_garbage_collection()` 方法执行两步清理：

1.  **清理过期的业务关联**: 删除 `th_jobs` 表中 `last_requested_at` 早于保留期限的记录。
2.  **清理孤立的内容**: 删除 `th_content` 中**不再被任何 `th_jobs` 或 `th_translations` 记录引用**的“孤立”记录。

    .. important::
       由于外键约束设置了 `ON DELETE CASCADE`，当一条孤立的 `th_content` 记录被删除时，所有与之关联的 `th_jobs` 和 `th_translations` 记录也会被自动、安全地一并清理。

核心概念辨析
------------

- **`business_id` (身份标识)**: 存储在独立的 `th_jobs` 表中，用于**生命周期管理**和来源追踪。它不影响翻译过程本身。
- **`context` (翻译情境)**: 其哈希值存储在 `th_translations` 表的 `context_id` 关联中，用于区分不同情境下的翻译。它的主要作用是**影响翻译结果**。

我们推荐为 `business_id` 使用一种带命名空间的、点分式的路径结构，例如 `ui.login-page.title` 或 `db.products.42.description`。
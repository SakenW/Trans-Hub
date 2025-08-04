.. # docs/guides/data_model.rst

=============================
数据库模型与 Schema (v3.0)
=============================

:文档目的: 本文档是 `Trans-Hub v3.0` 项目数据模型和数据库 Schema 的权威规范。

数据库要求
----------
- **默认实现**: **SQLite**。
- **数据库迁移**: 通过独立的 `schema_manager.py` 和 SQL 文件进行管理。

数据实体关系图 (ERD)
--------------------

.. mermaid::

   erDiagram
       th_content {
           TEXT id PK
           TEXT business_id UK "Stable Reference ID"
           TEXT source_payload_json JSON
       }
       th_contexts {
           TEXT id PK
           TEXT context_hash UK "Snapshot Hash"
           TEXT context_payload_json JSON
       }
       th_jobs {
           TEXT id PK
           TEXT content_id FK
           TIMESTAMP last_requested_at
       }
       th_translations {
           TEXT id PK
           TEXT content_id FK
           TEXT context_id FK
           TEXT lang_code
           TEXT status
           TEXT translation_payload_json JSON
       }
       th_content ||--|{ th_jobs : "is tracked by"
       th_content ||--o{ th_translations : "has"
       th_contexts ||--o{ th_translations : "applies to"

Schema 详解
-----------

### `th_content` (源实体层)

- **职责**: 存储所有唯一的、权威的源内容。这是所有翻译的“单一事实来源”。
- **核心字段**:
  - `id`: 内部 UUID。
  - `business_id`: **稳定引用 ID**，对外暴露，全局唯一。
  - `source_payload_json`: 存储结构化原始内容的 JSON 对象。

### `th_contexts` (上下文快照层)

- **职责**: 存储唯一的上下文“快照”及其哈希值。
- **核心字段**:
  - `context_hash`: 对上下文 payload 标准化后计算的哈希，用于快速查找。
  - `context_payload_json`: 实际的上下文 JSON 对象。

### `th_jobs` (任务跟踪)

- **职责**: 记录对一个 `content_id` 的最新请求时间，主要用于**垃圾回收**。

### `th_translations` (衍生层)

- **职责**: 存储一个内容针对特定语言和上下文的翻译结果及其生命周期状态。这是系统的核心操作表。

### `th_dead_letter_queue` (死信队列)

- **职责**: 存放处理失败且无法自动恢复的任务。

### `th_audit_logs` (审计日志)

- **职责**: 统一的、不可变的、记录所有重要事件的日志。
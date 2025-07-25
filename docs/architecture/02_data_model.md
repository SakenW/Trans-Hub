# **数据模型与数据库设计 (v2.0)**

**本文档的目标读者**: 核心维护者、数据库管理员，以及需要直接与数据库交互或理解数据持久化逻辑的开发者。

**文档目的**: 本文档是 `Trans-Hub` 项目数据模型和数据库 Schema 的权威规范。它详尽地描述了每个表的结构、字段含义、索引和设计决策。

---

## **1. 数据库支持与要求**

- **默认实现**: **SQLite**。为保证高并发性能，**必须以 WAL (Write-Ahead Logging) 模式运行**。该设置已包含在初始迁移脚本中。
- **原子性要求**: `PersistenceHandler` 的所有写操作**必须是事务性原子操作**。
- **数据库迁移**: 迁移通过独立的 `schema_manager.py` 和 SQL 文件进行管理，是部署和应用启动时的必要步骤。

---

## **2. 数据库 Schema**

### **2.1 `th_content` (内容表)**

- **职责**: 存储所有唯一的、去重后的文本字符串。这是所有翻译的“单一事实来源”。
- **字段**:
  - `id` (INTEGER PRIMARY KEY): 唯一标识符。
  - `value` (TEXT, UNIQUE): 文本内容本身。
  - `created_at` (TIMESTAMP): 记录创建时间。
- **索引**:
  - **`idx_th_content_value` (在 `value` 列上)**: **[性能关键]** 此索引对于快速根据文本内容查找 `content_id` 至关重要，显著提升了 `save_translations` 和 `ensure_pending_translations` 的性能。

### **2.2 `th_sources` (来源表)**

- **职责**: 建立业务逻辑标识符 (`business_id`) 与具体内容 (`content_id`) 和上下文 (`context_hash`) 之间的权威关联。
- **字段**:
  - `business_id` (TEXT, PRIMARY KEY): 上层应用定义的唯一业务标识符。
  - `content_id` (INTEGER, FK to `th_content.id`): 关联的内容 ID。
  - `context_hash` (TEXT, NOT NULL): 关联的上下文哈希。使用 `'__GLOBAL__'` 表示无特定上下文。
  - `last_seen_at` (TIMESTAMP): 用于**垃圾回收**的时间戳，每次 `request` 关联此 `business_id` 时更新。

### **2.3 `th_translations` (译文表)**

- **职责**: 存储一个内容针对特定语言和上下文的翻译结果及其生命周期状态。
- **字段**:
  - `id` (INTEGER PRIMARY KEY): 唯一标识符。
  - `content_id` (INTEGER, FK to `th_content.id`, ON DELETE CASCADE): 关联的内容 ID。当 `th_content` 中的一条记录被删除时，所有引用它的翻译记录都将被**级联删除**。
  - `source_lang_code` (TEXT, NULLABLE): 源语言代码，`NULL` 表示由引擎自动检测。
  - `lang_code` (TEXT, NOT NULL): 目标语言代码 (例如, 'en', 'zh-CN')。
  - `context_hash` (TEXT, NOT NULL): 上下文哈希。
  - `context` (TEXT, JSON, NULLABLE): 存储与此翻译任务关联的原始上下文 `dict` 的 JSON 字符串表示。
  - `translation_content` (TEXT, NULLABLE): 翻译后的文本。`NULL` 表示尚未翻译或翻译失败。
  - `engine` (TEXT, NULLABLE): 执行翻译的引擎名称。
  - `engine_version` (TEXT, NULLABLE): 执行翻译时引擎的版本号。在任务入队时记录。
  - `status` (TEXT, NOT NULL): 任务状态 (例如 `PENDING`, `TRANSLATING`, `TRANSLATED`, `FAILED`)。
  - `last_updated_at` (TIMESTAMP, NOT NULL): 记录的最后更新时间。
- **约束与索引**:
  - **`UNIQUE(content_id, lang_code, context_hash)`**: 保证了对于同一原文、同一目标语言、同一上下文，只存在一条翻译记录。
  - **`idx_th_translations_lookup`**: 覆盖 `(lang_code, status)` 等字段，用于高效地查询待处理任务 (`stream_translatable_items`)。

---

## **3. 垃圾回收 (GC)**

`Coordinator.run_garbage_collection()` 方法执行以下两步清理：

1.  **清理过期的业务关联**: 删除 `th_sources` 表中 `last_seen_at` 早于保留期限的记录。
    - 此操作支持 `dry_run` 模式，允许在不实际删除数据的情况下预览清理报告。
2.  **清理孤立的内容**: 删除 `th_content` 中**不再被任何 `th_sources` 或 `th_translations` 记录引用**的“孤立”记录。
    - **重要**: 由于外键约束设置了 `ON DELETE CASCADE`，当一条孤立的 `th_content` 记录被删除时，所有与之关联的 `th_translations` 记录也会被自动、安全地一并清理。

---

## **4. `business_id` 与 `context` 的作用**

这两个概念是 `Trans-Hub` 设计的核心，它们的区别和用途在 [\*\*高级用法指南](../guides/02_advanced_usage.md)\*\* 中有详细的示例。在此，我们重申其在数据模型中的作用：

- **`business_id`**: **身份标识**。它存储在独立的 `th_sources` 表中，用于**生命周期管理**和来源追踪。它不影响翻译过程本身。
- **`context`**: **翻译情境**。它被哈希并存储在 `th_translations` 表的 `context_hash` 字段中，用于区分不同情境下的翻译。它的主要作用是**影响翻译结果**。不同的 `context` 会生成不同的 `context_hash`，从而导致创建独立的翻译记录。

### **推荐的 `business_id` 命名约定**

我们推荐使用一种**带命名空间的、点分式的路径结构**，以保持清晰和可管理性。

- **UI 界面文本**: `ui.login-page.title`, `ui.settings.save-button`
- **数据库内容**: `db.products.42.description`
- **文件来源**: `docs.user-manual.chapter-1.title`

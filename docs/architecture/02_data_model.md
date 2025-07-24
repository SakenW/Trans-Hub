# **数据模型与数据库设计 (v2.0)**

**本文档的目标读者**: 核心维护者、数据库管理员，以及需要直接与数据库交互或理解数据持久化逻辑的开发者。

**文档目的**: 本文档是 `Trans-Hub` 项目数据模型和数据库 Schema 的权威规范。它详尽地描述了每个表的结构、字段含义、索引和设计决策。

---

## **1. 数据库支持与要求**

- **默认实现**: **SQLite**。为保证高并发性能，**必须以 WAL (Write-Ahead Logging) 模式运行**。
- **原子性要求**: `PersistenceHandler` 的所有写操作**必须是事务性原子操作**。
- **数据库迁移**: 迁移通过独立的 `schema_manager.py` 和 SQL 文件进行管理，应作为显式的部署步骤执行。

---

## **2. 数据库 Schema**

### **2.1 `th_content` (内容表)**

- **职责**: 存储所有唯一的、去重后的文本字符串。
- **字段**:
  - `id` (INTEGER PRIMARY KEY): 唯一标识符。
  - `value` (TEXT, UNIQUE): 文本内容本身。
  - `created_at` (TIMESTAMP): 记录创建时间。

### **2.2 `th_sources` (来源表)**

- **职责**: 建立业务逻辑标识符 (`business_id`) 与具体内容 (`content_id`) 和上下文 (`context_hash`) 之间的权威关联。
- **字段**:
  - `business_id` (TEXT, PRIMARY KEY): 上层应用定义的唯一业务标识符。
  - `content_id` (INTEGER, FK to `th_content.id`, ON DELETE CASCADE): 关联的内容 ID。**当源内容被删除时，此关联记录也会被级联删除。**
  - `context_hash` (TEXT, NOT NULL): 关联的上下文哈希。使用 `GLOBAL_CONTEXT_SENTINEL` (`'__GLOBAL__'`) 表示无特定上下文。
  - `last_seen_at` (TIMESTAMP): 用于**垃圾回收**的时间戳，每次 `request` 关联此 `business_id` 时更新。
- **索引**: `(last_seen_at)`, `(content_id)`。

### **2.3 `th_translations` (译文表)**

- **职责**: 存储一个内容针对特定语言和上下文的翻译结果及其元数据。
- **字段**:
  - `id` (INTEGER PRIMARY KEY): 唯一标识符。
  - `content_id` (INTEGER, FK to `th_content.id`, ON DELETE CASCADE): 关联的内容 ID。当源内容被删除时，相关的翻译记录也会被级联删除。
  - `source_lang_code` (TEXT, NULLABLE): 源语言代码，`NULL` 表示由引擎自动检测。
  - `lang_code` (TEXT, NOT NULL): 目标语言代码 (例如, 'en', 'zh-CN')。
  - `context_hash` (TEXT, NOT NULL): 上下文哈希。
  - `context` (TEXT, JSON, NULLABLE): 存储与此翻译任务关联的原始上下文 `dict` 的 JSON 字符串表示。
  - `translation_content` (TEXT, NULLABLE): 翻译后的文本。
  - `engine` (TEXT, NULLABLE): 执行翻译的引擎名称。
  - **[核心修正]** `engine_version` (TEXT, NULLABLE): 引擎的版本号。在 `PENDING` 状态下为空。
  - `status` (TEXT, NOT NULL): 任务状态 (例如 `PENDING`, `TRANSLATING`, `TRANSLATED`, `FAILED`)。
  - `last_updated_at` (TIMESTAMP, NOT NULL): 记录的最后更新时间。
- **约束**: `UNIQUE(content_id, lang_code, context_hash)` 保证了翻译的唯一性。

---

## **3. 垃圾回收 (GC)**

`Coordinator.run_garbage_collection()` 方法执行以下两步清理：

1.  **清理过期的业务关联**: 删除 `th_sources` 表中 `last_seen_at` 早于保留期限的记录。
    - **核心实现**: 此操作通过日期比较 (`WHERE DATE(last_seen_at) < ?`) 来实现，使其行为在单次运行的脚本中也变得完全可预测和健壮。
    - 此操作支持 `dry_run` 模式，允许在不实际删除数据的情况下预览清理报告。
2.  **清理孤立的内容**: 删除 `th_content` 中**不再被任何 `th_sources` 或 `th_translations` 记录引用**的“孤立”记录。

**重要提示**：`GC` 仅清理 `th_sources` 中过期的**业务关联**。如果 `th_translations` 中存在某个翻译结果，但其关联的 `business_id` 在 `th_sources` 中被清理，则该翻译结果本身仍会保留，除非其 `content_id` 变得完全孤立。

---

## **4. `business_id` 命名指南与最佳实践**

`business_id` 是 `Trans-Hub` 设计中的一个核心概念。它是一个由上层应用定义的、全局唯一的字符串，其主要目的是**将一段具体的文本内容与它在业务逻辑中出现的“位置”或“来源”进行稳定地关联**。

### **4.1 `business_id` 与数据流**

- `business_id` **主要存储在 `th_sources` 表**，并与 `content_id` 及 `context_hash` 构成唯一组合。它在 `th_sources` 表中的 `last_seen_at` 字段用于 `GC`。
- `th_translations` 表**不存储 `business_id`**，以避免数据冗余。
- `Coordinator` 在生成最终的 `TranslationResult` 时，会根据 `content_id` 和 `context_hash` **动态地从 `th_sources` 表查询对应的 `business_id`**。如果 `th_sources` 中没有匹配的记录（例如被 `GC` 清理了），则 `TranslationResult` 的 `business_id` 将为 `None`。

### **4.2 推荐的命名约定**

我们推荐使用一种**带命名空间的、点分式的路径结构**：`domain.subdomain.component.key`。例如，`ui.login_page.title`。

### **4.3 命名示例**

- **UI 界面文本**: `ui.login-page.title`, `ui.settings.save-button`
- **配置文件**: `config.plugin-manifest.name`
- **数据库内容**: `db.products.42.description`
- **即席翻译**: 调用 `request()` 时，将 `business_id` 参数设为 `None`。这种一次性翻译的 `TranslationResult` 将始终显示 `business_id: None`。

一个好的 `business_id` 命名规范将使您的本地化项目在规模扩大时依然能够保持清晰和易于管理。

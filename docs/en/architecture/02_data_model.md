# **Data Model and Database Design (v2.0)**

The target audience of this document: core maintainers, database administrators, and developers who need to interact directly with the database or understand data persistence logic.

**Document Purpose**: This document is the authoritative specification of the data model and database schema for the `Trans-Hub` project. It provides a detailed description of the structure of each table, the meaning of the fields, indexes, and design decisions.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **1. Database Support and Requirements**

- **Default Implementation**: **SQLite**. To ensure high concurrency performance, **it must run in WAL (Write-Ahead Logging) mode**. This setting is included in the initial migration script.
- **Atomicity Requirement**: All write operations of `PersistenceHandler` **must be transactional atomic operations**.
- **Database Migration**: Migration is managed through a separate `schema_manager.py` and SQL files, which is a necessary step during deployment and application startup.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **2. Database Schema**

### **2.1 `th_content` (Content Table)**

- **Responsibilities**: Store all unique, deduplicated text strings. This is the "single source of truth" for all translations.
- **Fields**:
  - `id` (INTEGER PRIMARY KEY): Unique identifier.
  - `value` (TEXT, UNIQUE): The text content itself.
  - `created_at` (TIMESTAMP): Record creation time.
- **Indexes**:
  - **`idx_th_content_value` (on `value` column)**: **[Performance Critical]** This index is crucial for quickly looking up `content_id` based on text content, significantly improving the performance of `save_translations` and `ensure_pending_translations`.

### **2.2 `th_sources` (Source Table)**

- **Responsibilities**: Establish an authoritative association between the business logic identifier (`business_id`), specific content (`content_id`), and context (`context_hash`).
- **Fields**:
  - `business_id` (TEXT, PRIMARY KEY): A unique business identifier defined by the upper-level application.
  - `content_id` (INTEGER, FK to `th_content.id`): The associated content ID.
  - `context_hash` (TEXT, NOT NULL): The associated context hash. Use `'__GLOBAL__'` to indicate no specific context.
  - `last_seen_at` (TIMESTAMP): A timestamp for **garbage collection**, updated each time a `request` associates with this `business_id`.

### **2.3 `th_translations` (Translation Table)**

- **Responsibilities**: Store a translation result for specific languages and contexts along with its lifecycle status.
- **Fields**:
  - `id` (INTEGER PRIMARY KEY): Unique identifier.
  - `content_id` (INTEGER, FK to `th_content.id`, ON DELETE CASCADE): Associated content ID. When a record in `th_content` is deleted, all translation records referencing it will be **cascaded deleted**.
  - `source_lang_code` (TEXT, NULLABLE): Source language code, `NULL` indicates automatic detection by the engine.
  - `lang_code` (TEXT, NOT NULL): Target language code (e.g., 'en', 'zh-CN').
  - `context_hash` (TEXT, NOT NULL): Context hash.
  - `context` (TEXT, JSON, NULLABLE): JSON string representation of the original context `dict` associated with this translation task.
  - `translation_content` (TEXT, NULLABLE): Translated text. `NULL` indicates not yet translated or translation failed.
  - `engine` (TEXT, NULLABLE): Name of the engine performing the translation.
  - `engine_version` (TEXT, NULLABLE): Version number of the engine at the time of translation. Recorded when the task is queued.
  - `status` (TEXT, NOT NULL): Task status (e.g., `PENDING`, `TRANSLATING`, `TRANSLATED`, `FAILED`).
  - `last_updated_at` (TIMESTAMP, NOT NULL): Last updated time of the record.
- **Constraints and Indexes**:
  - **`UNIQUE(content_id, lang_code, context_hash)`**: Ensures that there is only one translation record for the same original text, target language, and context.
  - **`idx_th_translations_lookup`**: Covers fields like `(lang_code, status)` for efficient querying of pending tasks (`stream_translatable_items`).

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **3. Garbage Collection (GC)**

The `Coordinator.run_garbage_collection()` method performs the following two cleanup steps:

1. **Clean up expired business associations**: Delete records in the `th_sources` table where `last_seen_at` is earlier than the retention period.
   - This operation supports `dry_run` mode, allowing a preview of the cleanup report without actually deleting data.
2. **Clean up isolated content**: Delete "isolated" records in `th_content` that are **no longer referenced by any `th_sources` or `th_translations` records**.
   - **Important**: Due to foreign key constraints set to `ON DELETE CASCADE`, when an isolated `th_content` record is deleted, all associated `th_translations` records will also be automatically and safely cleaned up.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **4. The Role of `business_id` and `context`**

These two concepts are the core of the `Trans-Hub` design, and their differences and uses are detailed in the [**Advanced Usage Guide**](../guides/02_advanced_usage.md). Here, we reiterate their role in the data model:

- **`business_id`**: **Identity identifier**. It is stored in the separate `th_sources` table and is used for **lifecycle management** and source tracking. It does not affect the translation process itself.
- **`context`**: **Translation context**. It is hashed and stored in the `context_hash` field of the `th_translations` table to distinguish translations in different contexts. Its main function is to **affect the translation results**. Different `context` will generate different `context_hash`, leading to the creation of independent translation records.

### **Recommended `business_id` Naming Convention**

We recommend using a **namespace-based, dot-separated path structure** to maintain clarity and manageability.

- **UI Interface Text**: `ui.login-page.title`, `ui.settings.save-button`
- **Database Content**: `db.products.42.description`
- **File Source**: `docs.user-manual.chapter-1.title`

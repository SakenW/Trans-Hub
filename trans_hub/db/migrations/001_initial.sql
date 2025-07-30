-- trans_hub/db/migrations/001_initial.sql
-- Trans-Hub Schema: Version 1.1 (Final)
-- 核心修复：
-- 1. 使用正确的 SQL 注释语法 (`--` 而不是 `#`)。
-- 2. 使用两个部分唯一索引 (Partial Unique Indexes) 来替代有缺陷的 UNIQUE 约束，
--    以正确处理包含 NULL 值的唯一性，这是保证 ON CONFLICT 逻辑正确的关键。

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- 1. 元数据表
CREATE TABLE IF NOT EXISTS th_meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO th_meta (key, value) VALUES ('schema_version', '1');

-- 2. 上下文表
CREATE TABLE IF NOT EXISTS th_contexts (
    id TEXT PRIMARY KEY,
    context_hash TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL
);

-- 3. 内容表
CREATE TABLE IF NOT EXISTS th_content (
    id TEXT PRIMARY KEY,
    value TEXT NOT NULL UNIQUE
);

-- 4. 任务/请求表
CREATE TABLE IF NOT EXISTS th_jobs (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    content_id TEXT NOT NULL,
    context_id TEXT,
    last_requested_at TIMESTAMP NOT NULL,
    FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE,
    FOREIGN KEY(context_id) REFERENCES th_contexts(id) ON DELETE SET NULL
);

-- 5. 译文表
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

-- 6. 死信队列
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

-- 索引定义
CREATE INDEX IF NOT EXISTS idx_jobs_last_requested_at ON th_jobs(last_requested_at);
CREATE INDEX IF NOT EXISTS idx_translations_status_lang ON th_translations(status, lang_code);
CREATE INDEX IF NOT EXISTS idx_dlq_failed_at ON th_dead_letter_queue(failed_at);

-- --- 最终修复：使用部分唯一索引来保证正确的唯一性 ---
-- Jobs 表的唯一性
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_unique_with_context
ON th_jobs(business_id, content_id, context_id)
WHERE context_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_unique_without_context
ON th_jobs(business_id, content_id)
WHERE context_id IS NULL;

-- Translations 表的唯一性
CREATE UNIQUE INDEX IF NOT EXISTS idx_translations_unique_with_context
ON th_translations(content_id, lang_code, context_id)
WHERE context_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_translations_unique_without_context
ON th_translations(content_id, lang_code)
WHERE context_id IS NULL;
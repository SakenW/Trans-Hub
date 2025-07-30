-- Trans-Hub Schema: Version 3.2 (The Genesis Block - Ultimate Compatibility)
-- 核心特性：
-- 1. UUID 主键。
-- 2. 'jobs' 表原子关联。
-- 3. 使用最标准的 SQL 语法，不依赖任何特定数据库方言的高级特性，
--    以保证未来向 PostgreSQL, MySQL 等数据库迁移的最大平滑度。

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
    FOREIGN KEY(context_id) REFERENCES th_contexts(id) ON DELETE SET NULL,
    -- 标准 UNIQUE 约束，它会自然忽略包含 NULL 的行
    UNIQUE(business_id, content_id, context_id)
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
    last_updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE,
    FOREIGN KEY(context_id) REFERENCES th_contexts(id) ON DELETE SET NULL,
    UNIQUE(content_id, lang_code, context_id)
);

-- 6. 死信队列
CREATE TABLE IF NOT EXISTS th_dead_letter_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_content TEXT NOT NULL, source_lang_code TEXT,
    target_lang_code TEXT NOT NULL, context_hash TEXT NOT NULL,
    context_json TEXT, engine_name TEXT, engine_version TEXT,
    last_error_message TEXT NOT NULL,
    failed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 索引定义
CREATE INDEX IF NOT EXISTS idx_jobs_last_requested_at ON th_jobs(last_requested_at);
CREATE INDEX IF NOT EXISTS idx_translations_status_lang ON th_translations(status, lang_code);
CREATE INDEX IF NOT EXISTS idx_dlq_failed_at ON th_dead_letter_queue(failed_at);
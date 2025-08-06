-- trans_hub/db/migrations/001_initial.sql
-- Trans-Hub v3.0.0 数据库基础 Schema
-- 本 Schema 基于 VCMP v1.5 "堡垒"架构思想设计，并为 Trans-Hub 的具体需求进行了定制。
-- 它引入了稳定引用ID、结构化载荷、上下文快照和审计日志等核心概念。

-- 开启外键约束支持
PRAGMA foreign_keys = ON;

-- 用于 Schema 版本管理的元数据表
CREATE TABLE IF NOT EXISTS th_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO th_meta (key, value) VALUES ('schema_version', '1');

-- =============================================================================
-- 实体层与上下文层 (基础定义)
-- =============================================================================

CREATE TABLE IF NOT EXISTS th_content (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL UNIQUE,
    source_payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc'))
);
CREATE INDEX IF NOT EXISTS idx_content_business_id ON th_content(business_id);

CREATE TABLE IF NOT EXISTS th_contexts (
    id TEXT PRIMARY KEY,
    context_hash TEXT NOT NULL UNIQUE,
    context_payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc'))
);
CREATE INDEX IF NOT EXISTS idx_contexts_hash ON th_contexts(context_hash);

-- =============================================================================
-- 衍生层 (翻译内容)
-- =============================================================================

CREATE TABLE IF NOT EXISTS th_translations (
    id TEXT PRIMARY KEY,
    content_id TEXT NOT NULL,
    context_id TEXT,
    lang_code TEXT NOT NULL,
    -- v3.x 修复：增加 source_lang 字段以支持多源语言
    source_lang TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',

    translation_payload_json TEXT,
    engine TEXT,
    engine_version TEXT,
    error TEXT,

    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc')),
    last_updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc')),

    FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE,
    FOREIGN KEY(context_id) REFERENCES th_contexts(id) ON DELETE CASCADE,
    CONSTRAINT uq_translation UNIQUE (content_id, context_id, lang_code)
);
CREATE INDEX IF NOT EXISTS idx_translations_status_lang ON th_translations(status, lang_code);

-- =============================================================================
-- 治理与审计层
-- =============================================================================

CREATE TABLE IF NOT EXISTS th_jobs (
    id TEXT PRIMARY KEY,
    content_id TEXT NOT NULL UNIQUE,
    last_requested_at TEXT NOT NULL,
    FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS th_dead_letter_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    translation_id TEXT,
    original_payload_json TEXT NOT NULL,
    context_payload_json TEXT,
    target_lang_code TEXT NOT NULL,
    last_error_message TEXT,
    failed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc')),
    engine_name TEXT,
    engine_version TEXT
);

CREATE TABLE IF NOT EXISTS th_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    user_id TEXT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc')),
    details_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_record ON th_audit_logs(table_name, record_id);
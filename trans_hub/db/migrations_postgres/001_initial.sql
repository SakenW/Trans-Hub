-- Trans-Hub v4.0 PostgreSQL 基础 Schema
-- 本 Schema 是对 SQLite v3.0 Schema 的直接翻译和适配，
-- 并利用了 PostgreSQL 的原生数据类型如 UUID 和 JSONB。

-- =============================================================================
-- 元数据表
-- =============================================================================
CREATE TABLE IF NOT EXISTS th_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO th_meta (key, value) VALUES ('schema_version', '1') ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- 实体层与上下文层
-- =============================================================================

CREATE TABLE IF NOT EXISTS th_content (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id TEXT NOT NULL UNIQUE,
    source_payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc'),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc')
);
CREATE INDEX IF NOT EXISTS idx_content_business_id ON th_content(business_id);

CREATE TABLE IF NOT EXISTS th_contexts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    context_hash TEXT NOT NULL UNIQUE,
    context_payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc')
);
CREATE INDEX IF NOT EXISTS idx_contexts_hash ON th_contexts(context_hash);

-- =============================================================================
-- 衍生层 (翻译内容)
-- =============================================================================

CREATE TABLE IF NOT EXISTS th_translations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_id UUID NOT NULL REFERENCES th_content(id) ON DELETE CASCADE,
    context_id UUID REFERENCES th_contexts(id) ON DELETE CASCADE,
    lang_code TEXT NOT NULL,
    -- v4.0 修复：增加 source_lang 字段以支持多源语言
    source_lang TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    
    translation_payload_json JSONB,
    engine TEXT,
    engine_version TEXT,
    error TEXT,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc'),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc'),
    
    UNIQUE(content_id, context_id, lang_code)
);
CREATE INDEX IF NOT EXISTS idx_translations_status_lang ON th_translations(status, lang_code);

-- =============================================================================
-- 治理与审计层
-- =============================================================================

CREATE TABLE IF NOT EXISTS th_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_id UUID NOT NULL UNIQUE REFERENCES th_content(id) ON DELETE CASCADE,
    last_requested_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS th_dead_letter_queue (
    id SERIAL PRIMARY KEY,
    translation_id UUID,
    original_payload_json JSONB NOT NULL,
    context_payload_json JSONB,
    target_lang_code TEXT NOT NULL,
    last_error_message TEXT,
    failed_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc'),
    engine_name TEXT,
    engine_version TEXT
);

CREATE TABLE IF NOT EXISTS th_audit_logs (
    id SERIAL PRIMARY KEY,
    event_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    user_id TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc'),
    details_json JSONB
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_record ON th_audit_logs(table_name, record_id);

-- =============================================================================
-- 事件驱动 Worker 支持 (LISTEN/NOTIFY)
-- =============================================================================

CREATE OR REPLACE FUNCTION notify_new_translation_task()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('new_translation_task', 'new');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS on_new_translation_task ON th_translations;
CREATE TRIGGER on_new_translation_task
    AFTER INSERT ON th_translations
    FOR EACH ROW
    WHEN (NEW.status = 'PENDING')
    EXECUTE FUNCTION notify_new_translation_task();
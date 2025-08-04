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

-- th_content: "源实体"层。存储最原始的、权威的内容。
-- 对应 VCMP 的 vcmp_source_entities。
CREATE TABLE IF NOT EXISTS th_content (
    id TEXT PRIMARY KEY,          -- 内部使用的 UUID
    business_id TEXT NOT NULL UNIQUE, -- 对外暴露的、稳定的业务ID，是“稳定内容引用”
    source_payload_json TEXT NOT NULL,  -- 存储原始内容的 JSON 对象
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc'))
);
CREATE INDEX IF NOT EXISTS idx_content_business_id ON th_content(business_id);

-- th_contexts: "上下文快照"层。代表一个唯一的上下文维度组合。
-- 对应 VCMP 的 vcmp_context_snapshots。
CREATE TABLE IF NOT EXISTS th_contexts (
    id TEXT PRIMARY KEY,          -- 内部使用的 UUID
    context_hash TEXT NOT NULL UNIQUE, -- 对规范化后的上下文 JSON 计算出的 SHA-256 哈希值
    context_payload_json TEXT NOT NULL,  -- 实际的上下文 JSON 对象
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc'))
);
CREATE INDEX IF NOT EXISTS idx_contexts_hash ON th_contexts(context_hash);

-- =============================================================================
-- 衍生层 (翻译内容)
-- =============================================================================

-- th_translations: "衍生品"层。存储翻译结果，并将其与实体和上下文关联。
-- 本表也隐式地承担了“关系层”的职责。
-- 对应 VCMP 的 vcmp_derivatives。
CREATE TABLE IF NOT EXISTS th_translations (
    id TEXT PRIMARY KEY,          -- 内部使用的 UUID
    content_id TEXT NOT NULL,
    context_id TEXT,              -- 可为空，代表全局上下文
    lang_code TEXT NOT NULL,      -- 目标语言代码，如 'en', 'zh-CN'
    status TEXT NOT NULL DEFAULT 'PENDING', -- 状态机: PENDING, TRANSLATING, TRANSLATED, FAILED, APPROVED
    
    translation_payload_json TEXT, -- 存储翻译后内容的 JSON 对象
    engine TEXT,                  -- 产生此翻译的引擎名称
    engine_version TEXT,
    error TEXT,
    
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc')),
    last_updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc')),
    
    FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE,
    FOREIGN KEY(context_id) REFERENCES th_contexts(id) ON DELETE CASCADE,
    UNIQUE(content_id, context_id, lang_code)
);
CREATE INDEX IF NOT EXISTS idx_translations_status_lang ON th_translations(status, lang_code);

-- =============================================================================
-- 治理与审计层
-- =============================================================================

-- th_jobs: 管理业务ID与翻译请求之间的关系，用于跟踪和更新。
-- 这是 Trans-Hub 的特有概念，用于简化任务更新逻辑。
CREATE TABLE IF NOT EXISTS th_jobs (
    id TEXT PRIMARY KEY,
    content_id TEXT NOT NULL,
    last_requested_at TEXT NOT NULL,
    FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE
);

-- th_dead_letter_queue: 用于存放处理失败且无法自动恢复的任务。
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

-- th_audit_logs: "审计日志"层。统一的、不可变的、记录所有重要事件的日志。
-- 对应 VCMP 的 vcmp_changelogs。
CREATE TABLE IF NOT EXISTS th_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,        -- 用于将单个事务中的多个事件分组的 UUID
    event_type TEXT NOT NULL,      -- 事件类型，如: 'CONTENT_CREATED', 'TRANSLATION_APPROVED'
    table_name TEXT NOT NULL,      -- 发生事件的表名，如: 'th_content', 'th_translations'
    record_id TEXT NOT NULL,
    user_id TEXT,                  -- 执行操作的用户ID (可选)
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'utc')),
    details_json TEXT              -- 包含相关细节的 JSON 对象，如数据变更的 diff
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_record ON th_audit_logs(table_name, record_id);
-- Trans-Hub Schema: Version 1 (基于 v0.1 最终版文档 - 最终最终修正版)
-- 本文件定义了 Trans-Hub 核心引擎的初始数据库结构。

-- ==============================================================================
--  PRAGMA 指令：SQLite 数据库初始化配置
-- ==============================================================================

-- 启用外键约束，这是保证数据关系完整性的关键。
PRAGMA foreign_keys = ON;

-- 使用 WAL (Write-Ahead Logging) 模式，显著提高并发性能。
PRAGMA journal_mode = WAL;


-- ==============================================================================
--  表定义
-- ==============================================================================

-- 1. 元数据表 (th_meta)
CREATE TABLE IF NOT EXISTS th_meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

-- 初始化 schema 版本号。
INSERT INTO th_meta (key, value) VALUES ('schema_version', '1');


-- 2. 内容表 (th_content)
CREATE TABLE IF NOT EXISTS th_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    value TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- 3. 来源表 (th_sources)
-- 将业务系统中的唯一标识符 (business_id) 与具体的内容和上下文进行关联。
CREATE TABLE IF NOT EXISTS th_sources (
    business_id TEXT PRIMARY KEY NOT NULL,
    content_id INTEGER NOT NULL,
    context_hash TEXT NOT NULL DEFAULT '__GLOBAL__',
    last_seen_at TIMESTAMP NOT NULL,
    
    FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE
);


-- 4. 译文表 (th_translations)
-- 存储每个内容针对不同语言、不同上下文的翻译结果。
CREATE TABLE IF NOT EXISTS th_translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL,
    
    source_lang_code TEXT,
    lang_code TEXT NOT NULL,
    context_hash TEXT NOT NULL DEFAULT '__GLOBAL__',

    translation_content TEXT,
    engine TEXT,
    engine_version TEXT NOT NULL,
    score REAL,

    -- business_id TEXT, -- <-- 核心修改：移除 th_translations.business_id 字段

    status TEXT NOT NULL CHECK(status IN ('PENDING', 'TRANSLATING', 'TRANSLATED', 'FAILED', 'APPROVED')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE,
    
    UNIQUE(content_id, lang_code, context_hash)
);


-- ==============================================================================
--  索引定义 (为了查询性能)
-- ==============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS idx_content_value ON th_content(value);
CREATE INDEX IF NOT EXISTS idx_sources_last_seen_at ON th_sources(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_translations_status_updated_at ON th_translations(status, last_updated_at);
CREATE INDEX IF NOT EXISTS idx_sources_content_id ON th_sources(content_id);
CREATE INDEX IF NOT EXISTS idx_translations_content_id ON th_translations(content_id);
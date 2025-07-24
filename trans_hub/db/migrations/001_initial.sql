-- Trans-Hub Schema: Version 1 (v2.0.0)
-- 本文件定义了 Trans-Hub 核心引擎的初始数据库结构。

-- ==============================================================================
--  PRAGMA 指令：SQLite 数据库初始化配置
-- ==============================================================================

-- 启用外键约束，这是保证数据关系完整性的关键。
PRAGMA foreign_keys = ON;

-- 使用 WAL (Write-Ahead Logging) 模式，显著提高并发读写性能。
PRAGMA journal_mode = WAL;


-- ==============================================================================
--  表定义
-- ==============================================================================

-- 1. 元数据表 (th_meta)
-- 用于存储数据库自身的元数据，如 schema 版本。
CREATE TABLE IF NOT EXISTS th_meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

-- 初始化 schema 版本号。
INSERT OR IGNORE INTO th_meta (key, value) VALUES ('schema_version', '1');


-- 2. 内容表 (th_content)
-- 存储唯一的、去重后的原始文本。
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
    context_hash TEXT NOT NULL,
    last_seen_at TIMESTAMP NOT NULL,
    
    -- --- 核心修正 1：添加 ON DELETE CASCADE 以确保参照完整性 ---
    FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE
);


-- 4. 译文表 (th_translations)
-- 存储每个内容针对不同语言、不同上下文的翻译结果。
CREATE TABLE IF NOT EXISTS th_translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL,
    
    source_lang_code TEXT,
    lang_code TEXT NOT NULL,
    context_hash TEXT NOT NULL,
    context TEXT, -- 存储原始上下文的 JSON 字符串

    translation_content TEXT,
    engine TEXT,
    -- --- 核心修正 2：移除 NOT NULL，因为 PENDING 状态下此字段为空 ---
    engine_version TEXT,
    score REAL,

    status TEXT NOT NULL CHECK(status IN ('PENDING', 'TRANSLATING', 'TRANSLATED', 'FAILED', 'APPROVED')),
    -- --- 核心修正 3：移除当前未被使用的字段，保持 Schema 简洁 ---
    -- retry_count INTEGER NOT NULL DEFAULT 0,
    last_updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE,
    
    -- 确保一个内容针对特定语言和上下文的翻译是唯一的
    UNIQUE(content_id, lang_code, context_hash)
);


-- ==============================================================================
--  索引定义 (为了查询性能)
-- ==============================================================================

-- 无需重复创建 UNIQUE 索引，因为 `value` 字段已有 UNIQUE 约束，SQLite 会自动为其创建索引。
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_content_value ON th_content(value);

CREATE INDEX IF NOT EXISTS idx_sources_last_seen_at ON th_sources(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_translations_status_updated_at ON th_translations(status, last_updated_at);
CREATE INDEX IF NOT EXISTS idx_sources_content_id ON th_sources(content_id);
CREATE INDEX IF NOT EXISTS idx_translations_content_id ON th_translations(content_id);
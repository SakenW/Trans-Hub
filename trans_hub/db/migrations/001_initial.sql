-- Trans-Hub Schema: Version 1
-- 本文件定义了 Trans-Hub 核心引擎的初始数据库结构。

-- PRAGMA 指令，对于 SQLite 至关重要
-- 启用外键约束，确保数据完整性
PRAGMA foreign_keys = ON;
-- 使用 WAL (Write-Ahead Logging) 模式，以提高并发性能和读写不阻塞
PRAGMA journal_mode = WAL;


-- 1. 元数据表 (th_meta)
-- 用于存储 schema 版本等内部元信息。
CREATE TABLE IF NOT EXISTS th_meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

-- 初始化 schema 版本号
INSERT INTO th_meta (key, value) VALUES ('schema_version', '1');


-- 2. 文本内容表 (th_texts)
-- 存储所有唯一的文本内容，以减少冗余。
CREATE TABLE IF NOT EXISTS th_texts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text_content TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 为 text_content 创建索引，以加速查找
CREATE UNIQUE INDEX IF NOT EXISTS idx_texts_content ON th_texts(text_content);


-- 3. 翻译记录表 (th_translations)
-- 存储每个文本针对不同语言、不同上下文的翻译结果。
CREATE TABLE IF NOT EXISTS th_translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text_id INTEGER NOT NULL,
    source_lang_code TEXT, -- 源语言，可为 NULL 表示由引擎自动检测
    lang_code TEXT NOT NULL, -- 目标语言
    context_hash TEXT, -- 上下文哈希，可为 NULL 表示全局翻译
    translation_content TEXT,
    engine TEXT, -- e.g., 'deepl', 'google', 'manual'
    engine_version TEXT NOT NULL,
    score REAL, -- 翻译质量得分，可选
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'TRANSLATING', 'TRANSLATED', 'FAILED', 'APPROVED')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 外键约束，当原始文本被删除时，级联删除所有相关翻译
    FOREIGN KEY(text_id) REFERENCES th_texts(id) ON DELETE CASCADE,
    
    -- 核心唯一性约束：一个文本、一种目标语言、一个上下文只能有一条翻译记录
    UNIQUE(text_id, lang_code, context_hash)
);

-- 为经常用于查询的列创建索引
CREATE INDEX IF NOT EXISTS idx_translations_status_updated_at ON th_translations(status, last_updated_at);
CREATE INDEX IF NOT EXISTS idx_translations_text_id ON th_translations(text_id);


-- 4. 业务来源表 (th_sources)
-- 将业务系统中的唯一标识符 (business_id) 与具体的文本和上下文进行关联。
CREATE TABLE IF NOT EXISTS th_sources (
    business_id TEXT PRIMARY KEY NOT NULL,
    text_id INTEGER NOT NULL,
    context_hash TEXT,
    last_seen_at TIMESTAMP NOT NULL,
    
    FOREIGN KEY(text_id) REFERENCES th_texts(id) ON DELETE CASCADE
);

-- 为垃圾回收 (GC) 和查询创建索引
CREATE INDEX IF NOT EXISTS idx_sources_last_seen_at ON th_sources(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_sources_text_id ON th_sources(text_id);
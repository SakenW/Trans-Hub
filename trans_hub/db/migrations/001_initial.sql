-- Trans-Hub Schema: Version 1 (基于 v0.1 最终版文档)
-- 本文件定义了 Trans-Hub 核心引擎的初始数据库结构。

-- ==============================================================================
--  PRAGMA 指令：SQLite 数据库初始化配置
-- ==============================================================================

-- 启用外键约束，这是保证数据关系完整性的关键。
-- 例如，确保 `th_translations` 中的 `content_id` 必须在 `th_content` 中存在。
PRAGMA foreign_keys = ON;

-- 使用 WAL (Write-Ahead Logging) 模式，显著提高并发性能。
-- 它允许读操作和写操作同时进行，而不会互相阻塞，对于Web应用或多线程应用至关重要。
PRAGMA journal_mode = WAL;


-- ==============================================================================
--  表定义
-- ==============================================================================

-- 1. 元数据表 (th_meta)
-- 用于存储 schema 版本等内部元信息，是数据库迁移管理的基础。
CREATE TABLE IF NOT EXISTS th_meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

-- 初始化 schema 版本号，标记数据库当前结构的版本。
INSERT INTO th_meta (key, value) VALUES ('schema_version', '1');


-- 2. 内容表 (th_content) [重大变更]
-- 存储所有唯一的、去重后的文本内容，避免数据冗余。
-- 从 `th_texts` 更名。
CREATE TABLE IF NOT EXISTS th_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    value TEXT NOT NULL UNIQUE, -- [变更] 列名从 `text_content` 改为 `value`。
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- 3. 来源表 (th_sources) [重大变更]
-- 将业务系统中的唯一标识符 (business_id) 与具体的内容和上下文进行关联。
CREATE TABLE IF NOT EXISTS th_sources (
    business_id TEXT PRIMARY KEY NOT NULL,
    content_id INTEGER NOT NULL, -- [变更] 列名从 `text_id` 改为 `content_id`。
    context_hash TEXT, -- 与此次关联绑定的上下文哈希，可为 NULL。
    last_seen_at TIMESTAMP NOT NULL, -- 用于垃圾回收 (GC) 的时间戳。
    
    -- [变更] 外键关联到 `th_content` 表。
    FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE
);


-- 4. 译文表 (th_translations) [重大变更]
-- 存储每个内容针对不同语言、不同上下文的翻译结果。
CREATE TABLE IF NOT EXISTS th_translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL, -- [变更] 列名从 `text_id` 改为 `content_id`。
    
    -- 语言与上下文
    source_lang_code TEXT, -- 源语言，可为 NULL 表示由引擎自动检测。
    lang_code TEXT NOT NULL, -- 目标语言。
    context_hash TEXT, -- 上下文哈希，可为 NULL 表示全局翻译。

    -- 翻译结果
    translation_content TEXT,
    engine TEXT, -- e.g., 'deepl', 'google', 'manual'
    engine_version TEXT NOT NULL,
    score REAL, -- 翻译质量得分，可选。

    -- 状态管理
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'TRANSLATING', 'TRANSLATED', 'FAILED', 'APPROVED')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- [变更] 外键关联到 `th_content` 表。
    FOREIGN KEY(content_id) REFERENCES th_content(id) ON DELETE CASCADE,
    
    -- [变更] 核心唯一性约束：一个内容、一种目标语言、一个上下文只能有一条翻译记录。
    UNIQUE(content_id, lang_code, context_hash)
);


-- ==============================================================================
--  索引定义 (为了查询性能)
-- ==============================================================================

-- 为 `th_content` 的 `value` 创建唯一索引，加速文本查找。
CREATE UNIQUE INDEX IF NOT EXISTS idx_content_value ON th_content(value);

-- 为 `th_sources` 的 `last_seen_at` 创建索引，加速垃圾回收查询。
CREATE INDEX IF NOT EXISTS idx_sources_last_seen_at ON th_sources(last_seen_at);

-- 为 `th_translations` 的 `(status, last_updated_at)` 创建复合索引，
-- 极大地加速 `stream_translatable_items` 方法中对 'PENDING' 状态的查询。
CREATE INDEX IF NOT EXISTS idx_translations_status_updated_at ON th_translations(status, last_updated_at);

-- 为所有外键列创建索引是数据库设计的最佳实践，可以提升 JOIN 操作的性能。
CREATE INDEX IF NOT EXISTS idx_sources_content_id ON th_sources(content_id);
CREATE INDEX IF NOT EXISTS idx_translations_content_id ON th_translations(content_id);
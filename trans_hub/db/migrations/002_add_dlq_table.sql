-- Trans-Hub Schema: Migration 2
--
-- 目的: 添加死信队列（Dead Letter Queue）表，用于归档永久失败的翻译任务。
--       这有助于保持主翻译表的清洁，并方便对失败任务进行分析和重试。

PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

-- 1. 创建死信队列（DLQ）表
CREATE TABLE th_dead_letter_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 原始任务信息
    original_content TEXT NOT NULL,
    source_lang_code TEXT,
    target_lang_code TEXT NOT NULL,
    context_hash TEXT NOT NULL,
    context_json TEXT,
    engine_name TEXT,
    engine_version TEXT,

    -- 失败元数据
    last_error_message TEXT NOT NULL,
    failed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. 为 DLQ 表创建索引以优化查询
CREATE INDEX IF NOT EXISTS idx_dlq_failed_at ON th_dead_letter_queue(failed_at);
CREATE INDEX IF NOT EXISTS idx_dlq_engine_name ON th_dead_letter_queue(engine_name);


-- 3. 更新 schema 版本号
UPDATE th_meta SET value = '2' WHERE key = 'schema_version';

COMMIT;
PRAGMA foreign_keys = ON;
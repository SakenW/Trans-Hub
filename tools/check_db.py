#!/usr/bin/env python3
import os
import sqlite3

# 数据库文件路径（默认值，与TransHubConfig中的默认值一致）
db_path = "transhub.db"

# 检查数据库文件是否存在
if not os.path.exists(db_path):
    print(f"错误: 数据库文件 '{db_path}' 不存在。")
    exit(1)

# 连接数据库
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    print(f"成功连接到数据库: {db_path}")

    # 检查是否存在预期的表
    expected_tables = [
        "th_meta",
        "th_contexts",
        "th_content",
        "th_jobs",
        "th_translations",
        "th_dead_letter_queue",
    ]
    for table in expected_tables:
        cursor.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
        )
        result = cursor.fetchone()
        if result:
            print(f"✅ 表 '{table}' 存在。")
        else:
            print(f"❌ 表 '{table}' 不存在！")

    # 检查schema版本
    cursor.execute("SELECT value FROM th_meta WHERE key = 'schema_version'")
    result = cursor.fetchone()
    if result:
        print(f"当前数据库schema版本: {result[0]}")
    else:
        print("❌ 无法确定数据库schema版本！")

except sqlite3.Error as e:
    print(f"数据库操作错误: {e}")
finally:
    if conn:
        conn.close()
        print("数据库连接已关闭。")

# examples/06_integration_with_file_system.py
"""
Trans-Hub v3.0 与文件系统集成示例

本示例模拟了一个常见的 CI/CD 场景：
1. 读取一个源语言的 JSON 字符串文件 (e.g., `en.json`)。
2. 遍历文件中的所有键值对，为它们创建翻译请求。
3. 启动 Worker 处理所有请求。
4. 获取所有翻译结果。
5. 将结果写入一个新的、按目标语言命名的 JSON 文件 (e.g., `de.json`)。
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Tuple

import structlog

# --- 路径设置 ---
current_dir = Path(__file__).parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
# ---

from trans_hub import Coordinator, TransHubConfig  # noqa: E402
from trans_hub.core.types import TranslationResult  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402

# --- 日志配置 ---
setup_logging(log_level="INFO")
log = structlog.get_logger(__name__)

# --- 准备测试环境 ---
DB_FILE = "th_example_06.db"
SOURCE_LANG = "en"
TARGET_LANGS = ["de", "fr"]
SOURCE_FILE = Path("en.json")
OUTPUT_DIR = Path("translations_output")


SOURCE_CONTENT = {
    "app_title": "My Awesome App",
    "buttons": {
        "submit": "Submit",
        "cancel": "Cancel"
    },
    "errors": {
        "network_error": "Failed to connect to the server."
    }
}


async def main() -> None:
    """执行文件系统集成示例。"""
    # 准备环境
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    SOURCE_FILE.write_text(json.dumps(SOURCE_CONTENT, indent=2))
    OUTPUT_DIR.mkdir(exist_ok=True)

    config = TransHubConfig(database_url=f"sqlite:///{DB_FILE}", source_lang=SOURCE_LANG)
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        await coordinator.initialize()

        # 1. 读取源文件并提交请求
        log.info(f"🚀 步骤 1: 读取源文件 '{SOURCE_FILE}' 并提交所有翻译请求...")
        source_data = json.loads(SOURCE_FILE.read_text())
        
        # 使用'点分隔'的键作为 business_id
        flat_source = flatten_dict(source_data)
        for business_id, text in flat_source.items():
            await coordinator.request(
                business_id=business_id,
                source_payload={"text": text},
                target_langs=TARGET_LANGS,
            )
        log.info(f"✅ 已为 {len(flat_source)} 个键提交请求。")

        # 2. Worker 处理
        async def process_translations_for_lang(language: str) -> None:
            # 消费异步生成器
            async for _ in coordinator.process_pending_translations(language):
                pass

        log.info("👷 步骤 2: Worker 正在处理所有任务...")
        worker_tasks: list[asyncio.Task[None]] = [
            asyncio.create_task(process_translations_for_lang(lang))
            for lang in TARGET_LANGS
        ]
        await asyncio.gather(*worker_tasks)
        log.info("✅ 所有任务处理完毕。")

        # 3. 获取结果并写入文件
        log.info("💾 步骤 3: 获取结果并写入目标文件...")
        for lang in TARGET_LANGS:
            lang_results = {}
            for business_id, _ in flat_source.items():
                result = await coordinator.get_translation(
                    business_id=business_id, target_lang=lang
                )
                if result and result.translated_payload:
                    lang_results[business_id] = result.translated_payload.get("text")
            
            # 将扁平的字典恢复为嵌套结构
            nested_results = unflatten_dict(lang_results)
            output_file = OUTPUT_DIR / f"{lang}.json"
            output_file.write_text(json.dumps(nested_results, indent=2, ensure_ascii=False))
            log.info(f"🎉 成功写入文件: '{output_file}'")

    finally:
        await coordinator.close()
        # 清理环境
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        if SOURCE_FILE.exists():
            SOURCE_FILE.unlink()
        if OUTPUT_DIR.exists():
            import shutil
            shutil.rmtree(OUTPUT_DIR)


def flatten_dict(d: dict[str, Any], parent_key: str = '', sep: str ='.') -> dict[str, Any]:
    """将嵌套字典扁平化。"""
    items: List[Tuple[str, Any]] = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def unflatten_dict(d: dict[str, Any], sep: str = '.') -> dict[str, Any]:
    """将扁平字典恢复为嵌套结构。"""
    result: dict[str, Any] = {}
    for key, value in d.items():
        parts = key.split(sep)
        d_ref = result
        for part in parts[:-1]:
            if part not in d_ref:
                d_ref[part] = {}
            d_ref = d_ref[part]
        d_ref[parts[-1]] = value
    return result


if __name__ == "__main__":
    asyncio.run(main())
    
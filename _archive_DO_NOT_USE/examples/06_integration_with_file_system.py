# examples/06_integration_with_file_system.py
"""
Trans-Hub v3.0 与文件系统集成示例 (重构版)
"""
import asyncio
import json
import shutil
from typing import Any
from examples._shared import example_runner, log, process_translations, current_dir

# --- 准备测试环境 ---
SOURCE_LANG = "en"
TARGET_LANGS = ["de", "fr"]
SOURCE_FILE = current_dir / "en.json"
OUTPUT_DIR = current_dir / "translations_output"
SOURCE_CONTENT = {
    "app_title": "My Awesome App",
    "buttons": {"submit": "Submit", "cancel": "Cancel"},
}

def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict[str, str]:
    items: list[tuple[str, str]] = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, str(v)))
    return dict(items)

def unflatten_dict(d: dict, sep: str = ".") -> dict:
    result: dict = {}
    for key, value in d.items():
        parts = key.split(sep)
        d_ref = result
        for part in parts[:-1]:
            d_ref = d_ref.setdefault(part, {})
        d_ref[parts[-1]] = value
    return result


async def main() -> None:
    """执行文件系统集成示例。"""
    # 准备文件和目录
    SOURCE_FILE.write_text(json.dumps(SOURCE_CONTENT, indent=2))
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir()

    try:
        async with example_runner("th_example_06.db", source_lang=SOURCE_LANG) as coordinator:
            log.info(f"🚀 步骤 1: 读取源文件并提交请求...")
            source_data = json.loads(SOURCE_FILE.read_text())
            flat_source = flatten_dict(source_data)
            for business_id, text in flat_source.items():
                await coordinator.request(
                    business_id=business_id,
                    source_payload={"text": text},
                    target_langs=TARGET_LANGS,
                )
            log.info(f"✅ 已为 {len(flat_source)} 个键提交请求。")

            log.info("👷 步骤 2: Worker 正在处理所有任务...")
            await process_translations(coordinator, TARGET_LANGS)

            log.info("💾 步骤 3: 获取结果并写入目标文件...")
            for lang in TARGET_LANGS:
                lang_results: dict[str, Any] = {}
                for business_id in flat_source:
                    result = await coordinator.get_translation(business_id=business_id, target_lang=lang)
                    if result and result.translated_payload:
                        lang_results[business_id] = result.translated_payload.get("text")

                nested_results = unflatten_dict(lang_results)
                output_file = OUTPUT_DIR / f"{lang}.json"
                output_file.write_text(json.dumps(nested_results, indent=2, ensure_ascii=False))
                log.info(f"🎉 成功写入文件: '{output_file}'")
    finally:
        # 清理文件和目录
        if SOURCE_FILE.exists(): SOURCE_FILE.unlink()
        if OUTPUT_DIR.exists(): shutil.rmtree(OUTPUT_DIR)

if __name__ == "__main__":
    asyncio.run(main())
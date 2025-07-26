# examples/translate_strings_file.py
"""
一个使用 Trans-Hub 库来翻译 Apple .strings 格式文件的示例程序。
此版本结合了 business_id 和动态生成的 context，以实现更精确的来源追踪和情境控制。
运行方式:
在项目根目录执行 `poetry run python examples/translate_strings_file.py`
"""

import asyncio
import re
import sys
from pathlib import Path

import structlog

# -- 路径设置 --
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trans_hub import (  # noqa: E402
    Coordinator,
    DefaultPersistenceHandler,
    TransHubConfig,
    TranslationStatus,
)
from trans_hub.db import schema_manager  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402

# ==============================================================================
#  输入数据
# ==============================================================================

STRINGS_CONTENT = """
/* Services */

"DEVONthink Pro: Lookup..." = "DEVONthink: Lookup…";
"DEVONthink Pro: Summarize" = "DEVONthink: Summarize";
"DEVONthink Pro: Take Plain Note" = "DEVONthink: Take Plain Note";
"DEVONthink Pro: Append Plain Note" = "DEVONthink: Append Plain Note";
"DEVONthink Pro: Append Rich Note" = "DEVONthink: Append Rich Note";
"DEVONthink Pro: Capture Web Archive" = "DEVONthink: Capture Web Archive";
"DEVONthink Pro: Capture Bookmark" = "DEVONthink: Capture Bookmark";
"DEVONthink Pro: Add To Reading List" = "DEVONthink: Add To Reading List. This is a longer description to test the context generation.";

"DEVONthink Pro/Take Rich Note" = "DEVONthink: Take Rich Note";
"DEVONthink Pro/Add To DEVONthink" = "Add to DEVONthink";

"DEVONthink Pro/Take Formatted Note" = "DEVONthink: Take Formatted Note";
"DEVONthink Pro: Take Markdown Note" = "DEVONthink: Take Markdown Note";
"DEVONthink Pro/Append Markdown Note" = "DEVONthink: Append Markdown Note";
"""

# ==============================================================================
#  动态上下文生成函数
# ==============================================================================


def generate_context_for_text(text: str) -> dict:
    """根据文本内容动态生成一个更精确的翻译上下文。"""
    base_context = {
        "source_app": "DEVONthink Pro",
        "file_type": ".strings",
    }
    word_count = len(text.split())
    if text.endswith("…"):
        base_context["text_type"] = "UI String (Menu Item)"
        base_context["note"] = (
            "Translate as a menu item that opens a dialog. Keep it concise."
        )
    elif any(p in text for p in ".?!"):
        base_context["text_type"] = "UI String (Descriptive Text)"
        base_context["note"] = (
            "Translate as a descriptive message or instruction. Ensure grammatical correctness."
        )
    elif word_count <= 5:
        base_context["text_type"] = "UI String (Label/Button)"
        base_context["note"] = (
            "Translate as a short button or label text. Be concise and direct."
        )
    else:
        base_context["text_type"] = "UI String (Generic)"
        base_context["note"] = "This is a generic UI string. Translate accurately."
    return base_context


# ==============================================================================
#  主程序
# ==============================================================================


async def main():
    """程序主入口"""
    setup_logging(log_level="INFO", log_format="console")
    log = structlog.get_logger()

    log.info("▶️ 翻译程序启动 (使用动态 context)...")

    db_file_path = Path(__file__).parent / "strings_translator_demo.db"
    log.info("临时数据库路径", path=str(db_file_path))
    db_file_path.unlink(missing_ok=True)

    log.info("▶️ 准备工作：应用数据库迁移...")
    try:
        schema_manager.apply_migrations(str(db_file_path))
        log.info("✅ 数据库迁移完成。")
    except Exception as e:
        log.error("数据库迁移失败，程序中止。", error=str(e), exc_info=True)
        return

    config = TransHubConfig()
    config.database_url = f"sqlite:///{db_file_path.resolve()}"
    handler = DefaultPersistenceHandler(config.db_path)

    coordinator = None
    try:
        coordinator = Coordinator(config=config, persistence_handler=handler)
        await coordinator.initialize()

        kv_pattern = re.compile(r'"([^"]+)"\s*=\s*"([^"]+)"\s*;')
        parsed_structure = []
        texts_to_translate = set()

        log.info("▶️ 第一步：解析 .strings 文件内容...")
        for line in STRINGS_CONTENT.strip().split("\n"):
            line = line.strip()
            if not line:
                parsed_structure.append(("blank", ""))
                continue
            match = kv_pattern.match(line)
            if match:
                key, value = match.groups()
                parsed_structure.append(("kv", (key, value)))
                texts_to_translate.add(value)
            else:
                parsed_structure.append(("comment", line))
        log.info("解析完成", unique_texts_found=len(texts_to_translate))

        log.info("▶️ 第二步：向 Trans-Hub 提交翻译请求...")
        if texts_to_translate:
            source_business_id = "devonthink_pro_services.strings"
            for text in texts_to_translate:
                dynamic_context = generate_context_for_text(text)
                await coordinator.request(
                    target_langs=["zh-CN"],
                    text_content=text,
                    source_lang="en",
                    business_id=source_business_id,
                    context=dynamic_context,
                )
        log.info("所有翻译任务已入队。", count=len(texts_to_translate))

        log.info("▶️ 第三步：执行翻译流程...")
        translation_results = {}
        async for result in coordinator.process_pending_translations(
            target_lang="zh-CN"
        ):
            if result.status == TranslationStatus.TRANSLATED:
                log.info(
                    "翻译成功",
                    original=f"'{result.original_content}'",
                    translated=f"'{result.translated_content}'",
                )
                translation_results[result.original_content] = result.translated_content
            else:
                log.error(
                    "翻译失败",
                    original=f"'{result.original_content}'",
                    error=result.error,
                )
                translation_results[result.original_content] = result.original_content

        log.info("▶️ 第四步：重建翻译后的文件...")
        output_lines = []
        for line_type, content in parsed_structure:
            if line_type == "blank":
                output_lines.append("")
            elif line_type == "comment":
                output_lines.append(content)
            elif line_type == "kv":
                key, original_value = content
                translated_value = translation_results.get(
                    original_value, original_value
                )
                output_lines.append(f'"{key}" = "{translated_value}";')

        log.info("✅ 翻译流程全部完成！")
        print("\n" + "=" * 20 + " 翻译结果 " + "=" * 20)
        print("\n".join(output_lines))
        print("=" * 52 + "\n")

    finally:
        if coordinator:
            await coordinator.close()
            log.info("数据库连接已关闭。")
            log.info("临时数据库已保留，请使用以下命令检查内容：")
            relative_db_path = db_file_path.relative_to(PROJECT_ROOT)
            print(f"\npoetry run python tools/inspect_db.py {relative_db_path}\n")


if __name__ == "__main__":
    asyncio.run(main())

# examples/03_specific_use_case_strings_file.py
"""
一个使用 Trans-Hub 库来翻译 Apple .strings 格式文件的示例程序。
此版本结合了 business_id 和动态生成的 context，以实现更精确的来源追踪和情境控制。

运行方式:
在项目根目录执行 `poetry run python examples/03_specific_use_case_strings_file.py`
"""

import asyncio
import re
import sys
from pathlib import Path

# --- 核心修正：导入所有需要的类型 ---
from typing import Any

import structlog

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trans_hub import Coordinator, TransHubConfig, TranslationStatus  # noqa: E402
from trans_hub.db import schema_manager  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402

STRINGS_CONTENT = """
/* Common */
"OK" = "OK";
"Cancel" = "Cancel";

/* Services */
"DEVONthink Pro: Lookup..." = "DEVONthink: Lookup…";
"DEVONthink Pro: Summarize" = "DEVONthink: Summarize";
"DEVONthink Pro: Take Plain Note" = "DEVONthink: Take Plain Note";
"DEVONthink Pro: Append Plain Note" = "DEVONthink: Append Plain Note";
"DEVONthink Pro: Add To Reading List" = "DEVONthink: Add To Reading List. This is a longer description.";
"""


def generate_context_for_text(text: str) -> dict[str, str]:
    """根据文本内容动态生成一个更精确的翻译上下文。"""
    base_context: dict[str, str] = {
        "source_app": "DEVONthink Pro",
        "file_type": ".strings",
    }
    if text.endswith("…"):
        base_context["text_type"] = "menu_item"
        base_context["note"] = (
            "Translate as a menu item that opens a dialog. Keep it concise."
        )
    elif len(text.split()) > 5:
        base_context["text_type"] = "descriptive_text"
        base_context["note"] = (
            "Translate as a descriptive message. Ensure grammatical correctness."
        )
    else:
        base_context["text_type"] = "label_or_button"
        base_context["note"] = (
            "Translate as a short button or label text. Be concise and direct."
        )
    return base_context


async def main() -> None:
    """程序主入口"""
    setup_logging(log_level="INFO", log_format="console")
    log = structlog.get_logger("strings_translator")

    db_file_path = Path(__file__).parent / "03_demo.db"
    db_file_path.unlink(missing_ok=True)

    log.info("▶️ 准备工作：应用数据库迁移...")
    schema_manager.apply_migrations(str(db_file_path.resolve()))

    config = TransHubConfig(database_url=f"sqlite:///{db_file_path.resolve()}")
    handler = create_persistence_handler(config)
    coordinator = None
    try:
        coordinator = Coordinator(config=config, persistence_handler=handler)
        await coordinator.initialize()

        kv_pattern = re.compile(r'"([^"]+)"\s*=\s*"([^"]+)"\s*;')
        # --- 核心修正：提供精确的类型注解 ---
        parsed_structure: list[tuple[str, Any]] = []
        texts_to_translate: set[str] = set()

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
            source_file_id = "devonthink_pro_services.strings"
            for text in texts_to_translate:
                dynamic_context = generate_context_for_text(text)
                await coordinator.request(
                    target_langs=["zh-CN"],
                    text_content=text,
                    source_lang="en",
                    business_id=source_file_id,
                    context=dynamic_context,
                )
        log.info("所有翻译任务已入队。", count=len(texts_to_translate))

        log.info("▶️ 第三步：执行翻译流程...")
        translation_results: dict[str, str] = {}
        async for result in coordinator.process_pending_translations(
            target_lang="zh-CN", limit=len(texts_to_translate)
        ):
            if (
                result.status == TranslationStatus.TRANSLATED
                and result.translated_content
            ):
                log.info(
                    f"翻译成功: '{result.original_content}' -> '{result.translated_content}'"
                )
                translation_results[result.original_content] = result.translated_content
            else:
                log.error(
                    f"翻译失败: '{result.original_content}' | Error: {result.error}"
                )
                translation_results[result.original_content] = (
                    f"ERROR: {result.original_content}"
                )

        log.info("▶️ 第四步：重建翻译后的文件...")
        output_lines: list[str] = []
        for line_type, content in parsed_structure:
            if line_type == "blank":
                output_lines.append("")
            elif line_type == "comment":
                # 明确断言 content 是字符串
                output_lines.append(str(content))
            elif line_type == "kv":
                # --- 核心修正：进行安全的解包 ---
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
        log.info("所有资源已关闭。")
        relative_db_path = db_file_path.relative_to(PROJECT_ROOT)
        print(
            f"数据库已保留，请使用以下命令检查内容：\npoetry run python tools/inspect_db.py {relative_db_path}\n"
        )


if __name__ == "__main__":
    asyncio.run(main())

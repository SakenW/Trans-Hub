# tools/doc_translator/synchronizer.py
import asyncio
from pathlib import Path
from typing import Any, Optional, List

import mistune
from mistune.renderers.markdown import MarkdownRenderer  # 导入正确的 v3 Markdown 渲染器
import structlog

from trans_hub import Coordinator
from trans_hub.types import TranslationResult

from .parser import parse_markdown

log = structlog.get_logger()
PROJECT_ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
SOURCE_LANG = "zh"
TARGET_LANGS = ["en"]

ROOT_DOCS_TO_MERGE = ["README", "CONTRIBUTING"]
SIMPLE_SYNC_FILES = ["RELEASE_SOP", "CHANGELOG"]

MAX_CONCURRENT_FILES = 5
MAX_CONCURRENT_DB_READS = 10


class TranslatedMarkdownRenderer(MarkdownRenderer):
    """
    [v3 最终版] 继承自 mistune v3 MarkdownRenderer 的自定义渲染器。
    通过重写 `text` 方法来应用翻译，这是最直接、最健壮的方式。
    """
    def __init__(self, translation_map: dict[str, str]):
        super().__init__()
        self.translation_map = translation_map

    def text(self, token: dict[str, Any], state: Any) -> str:
        # [核心修正] v3 的 text 方法接收一个 token 字典，而不是纯文本
        original_text = token.get("text", "")
        stripped_text = original_text.strip()
        
        translated_text = self.translation_map.get(stripped_text, original_text)
        
        # 更新 token 的内容，然后让父类处理转义等
        token["text"] = translated_text
        return super().text(token, state)


class DocSynchronizer:
    def __init__(self, coordinator: Coordinator):
        self.coordinator = coordinator
        self.file_semaphore = asyncio.Semaphore(MAX_CONCURRENT_FILES)
        self.db_read_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DB_READS)

    async def run_sync(self):
        source_files = list((DOCS_DIR / SOURCE_LANG).rglob("*.md"))
        if not source_files:
            log.warning(f"在 {DOCS_DIR / SOURCE_LANG} 中未找到任何源文件，同步中止。")
            return
        log.info(f"发现 {len(source_files)} 个源语言 ({SOURCE_LANG}) 文档文件。")

        log.info("\n---> [阶段 1/4] 并发扫描并登记所有任务 <---", concurrency=MAX_CONCURRENT_FILES)
        process_tasks = [self._process_source_file(sf) for sf in source_files]
        await asyncio.gather(*process_tasks)

        log.info("\n---> [阶段 2/4] 开始后台翻译处理 <---")
        for lang in TARGET_LANGS:
            async for _ in self.coordinator.process_pending_translations(lang):
                pass
        log.info("✅ 所有待办任务处理完成。")

        log.info("\n---> [阶段 3/4] 并发组装目标语言文件 <---", concurrency=MAX_CONCURRENT_DB_READS)
        assemble_tasks = [self._assemble_target_files(sf) for sf in source_files]
        await asyncio.gather(*assemble_tasks)
        log.info("✅ 所有目标语言文件组装完成。")

        log.info("\n---> [阶段 4/4] 智能同步文档到项目根目录 <---")
        self._sync_root_files()
        log.info("✅ 根目录文档同步完成。")

    async def _process_source_file(self, source_file: Path):
        async with self.file_semaphore:
            content = source_file.read_text("utf-8")
            blocks = parse_markdown(content)
            relative_path_str = str(source_file.relative_to(DOCS_DIR / SOURCE_LANG))
            for i, block in enumerate(blocks):
                business_id = f"docs.{relative_path_str}.{i:03d}.{block.stable_id[:8]}"
                await self.coordinator.request(
                    target_langs=TARGET_LANGS, text_content=block.source_text,
                    business_id=business_id, context={"block_type": block.node_type}
                )

    async def _assemble_target_files(self, source_file: Path):
        async with self.file_semaphore:
            source_content = source_file.read_text("utf-8")
            blocks_to_translate = parse_markdown(source_content)
            for lang in TARGET_LANGS:
                log.debug(f"正在组装: {source_file.name} -> {lang}")

                async def get_translation_throttled(block):
                    async with self.db_read_semaphore:
                        return await self.coordinator.get_translation(
                            text_content=block.source_text, target_lang=lang,
                            context={"block_type": block.node_type}
                        )

                tasks = [get_translation_throttled(block) for block in blocks_to_translate]
                results: List[Optional[TranslationResult]] = await asyncio.gather(*tasks)

                translation_map = {
                    b.source_text: (r.translated_content if r and r.translated_content else b.source_text)
                    for b, r in zip(blocks_to_translate, results)
                }
                
                renderer = TranslatedMarkdownRenderer(translation_map)
                markdown_parser = mistune.create_markdown(renderer=renderer)
                final_content = markdown_parser(source_content)

                relative_path = source_file.relative_to(DOCS_DIR / SOURCE_LANG)
                target_file_path = DOCS_DIR / lang / relative_path
                target_file_path.parent.mkdir(parents=True, exist_ok=True)
                target_file_path.write_text(final_content, "utf-8")

    def _sync_root_files(self):
        root_zh_dir = DOCS_DIR / "zh" / "root_sources"
        root_en_dir = DOCS_DIR / "en" / "root_sources"
        for doc_base_name in ROOT_DOCS_TO_MERGE:
            header_file, zh_file, en_file, dest_file = (
                root_zh_dir / f"_{doc_base_name}_HEADER.md",
                root_zh_dir / f"{doc_base_name}.zh.md",
                root_en_dir / f"{doc_base_name}.en.md",
                PROJECT_ROOT / f"{doc_base_name}.md",
            )
            if not header_file.exists() or not zh_file.exists():
                continue
            header = header_file.read_text("utf-8").strip()
            zh_content = zh_file.read_text("utf-8").strip()
            en_content = en_file.read_text("utf-8").strip() if en_file.exists() else ""
            if en_content:
                final_content = f"{header}\n\n---\n\n{zh_content}\n\n---\n\n<details>\n<summary><strong>English Version</strong></summary>\n\n{en_content}\n\n</details>\n"
            else:
                final_content = f"{header}\n\n---\n\n{zh_content}"
            log.info(f"正在生成多语言合并文件: {dest_file.name}")
            dest_file.write_text(final_content, "utf-8")
        for doc_base_name in SIMPLE_SYNC_FILES:
            source_file = root_zh_dir / f"{doc_base_name}.md"
            dest_file = PROJECT_ROOT / f"{doc_base_name}.md"
            if not source_file.exists():
                continue
            content = source_file.read_text("utf-8")
            en_path = str((DOCS_DIR / "en" / "root_sources" / f"{doc_base_name}.en.md").relative_to(PROJECT_ROOT)).replace("\\", "/")
            link = f'<div align="right">[English Version](./{en_path})</div>\n\n'
            log.info(f"正在生成单语言同步文件: {dest_file.name}")
            dest_file.write_text(link + content, "utf-8")
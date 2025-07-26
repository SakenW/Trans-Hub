# tools/doc_translator/synchronizer.py
import asyncio
from pathlib import Path

import structlog

from trans_hub import Coordinator, TranslationStatus

from .parser import parse_markdown

log = structlog.get_logger()
PROJECT_ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
SOURCE_LANG = "zh"
TARGET_LANGS = ["en"]

# [核心修复] 定义一个合理的并发限制，以避免数据库锁超时
MAX_CONCURRENT_FILES = 5

# 定义需要“智能合并”和“简单同步”的文件列表
# 智能合并，带 <details> 切换
ROOT_DOCS_TO_MERGE = ["README", "CONTRIBUTING"]
# 简单同步，只复制主语言版本并添加链接
SIMPLE_SYNC_FILES = ["RELEASE_SOP", "CHANGELOG"]


class DocSynchronizer:
    def __init__(self, coordinator: Coordinator):
        self.coordinator = coordinator
        # [核心修复] 初始化一个 Semaphore
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_FILES)

    async def run_sync(self):
        """执行完整的文档同步流程。"""
        source_files = list((DOCS_DIR / SOURCE_LANG).rglob("*.md"))

        if not source_files:
            log.warning(
                f"在 {DOCS_DIR / SOURCE_LANG} 中未找到任何源文件 (*.md)，同步中止。"
            )
            return

        log.info(f"发现 {len(source_files)} 个源语言 ({SOURCE_LANG}) 文档文件。")

        # 1. 并发扫描并登记所有任务 (受信号量限制)
        log.info(
            "\n---> [阶段 1/4] 并发扫描并登记所有任务 <---",
            concurrency=MAX_CONCURRENT_FILES,
        )
        process_tasks = [self._process_source_file(sf) for sf in source_files]
        await asyncio.gather(*process_tasks)

        # 2. 运行 Trans-Hub 后台处理
        log.info("\n---> [阶段 2/4] 开始后台翻译处理 <---")
        for lang in TARGET_LANGS:
            async for _ in self.coordinator.process_pending_translations(lang):
                pass
        log.info("✅ 所有待办任务处理完成。")

        # 3. 并发地重新组装所有目标语言文件
        log.info(
            "\n---> [阶段 3/4] 并发组装目标语言文件 <---",
            concurrency=MAX_CONCURRENT_FILES,
        )
        assemble_tasks = [self._assemble_target_files(sf) for sf in source_files]
        await asyncio.gather(*assemble_tasks)
        log.info("✅ 所有目标语言文件组装完成。")

        # 4. 智能地将 root_sources/ 的内容合并并同步到项目根目录
        log.info("\n---> [阶段 4/4] 智能同步文档到项目根目录 <---")
        self._sync_root_files()
        log.info("✅ 根目录文档同步完成。")

    async def _process_source_file(self, source_file: Path):
        """读取单个源文件，解析内容块，并向 Trans-Hub 提交翻译请求。"""
        # [核心修复] 在处理文件之前，先获取信号量
        async with self.semaphore:
            log.debug(f"正在扫描: {source_file.relative_to(PROJECT_ROOT)}")
            content = source_file.read_text("utf-8")
            blocks = parse_markdown(content)

            relative_path_str = str(source_file.relative_to(DOCS_DIR / SOURCE_LANG))

            for i, block in enumerate(blocks):
                business_id = f"docs.{relative_path_str}.{i:03d}.{block.stable_id[:8]}"
                context = {
                    "category": "technical_documentation",
                    "block_type": block.block_type,
                }

                await self.coordinator.request(
                    target_langs=TARGET_LANGS,
                    text_content=block.source_text,
                    business_id=business_id,
                    context=context,
                )

    async def _assemble_target_files(self, source_file: Path):
        """为一个源文件，生成所有目标语言的翻译版本，并处理 {lang} 占位符。"""
        # [核心修复] 同样，在组装文件时也使用信号量
        async with self.semaphore:
            source_content = source_file.read_text("utf-8")
            blocks = parse_markdown(source_content)

            for lang in TARGET_LANGS:
                translated_content = source_content

                tasks = [
                    self.coordinator.get_translation(
                        text_content=block.source_text,
                        target_lang=lang,
                        context={
                            "category": "technical_documentation",
                            "block_type": block.block_type,
                        },
                    )
                    for block in blocks
                ]
                results = await asyncio.gather(*tasks)

                for block, result in zip(blocks, results):
                    if (
                        result
                        and result.status == TranslationStatus.TRANSLATED
                        and result.translated_content
                    ):
                        translated_content = translated_content.replace(
                            block.source_text, result.translated_content
                        )

                final_content = translated_content.replace("{lang}", lang)

                relative_path = source_file.relative_to(DOCS_DIR / SOURCE_LANG)
                target_file_path = DOCS_DIR / lang / relative_path
                target_file_path.parent.mkdir(parents=True, exist_ok=True)
                target_file_path.write_text(final_content, "utf-8")

    def _sync_root_files(self):
        """根据不同的策略，将 docs/zh/root_sources/ 下的文档同步到项目根目录。"""
        root_zh_dir = DOCS_DIR / "zh" / "root_sources"
        root_en_dir = DOCS_DIR / "en" / "root_sources"

        # 策略 1: 智能合并，带 <details> 切换
        for doc_base_name in ROOT_DOCS_TO_MERGE:
            header_file = root_zh_dir / f"_{doc_base_name}_HEADER.md"
            zh_content_file = root_zh_dir / f"{doc_base_name}.zh.md"
            en_content_file = root_en_dir / f"{doc_base_name}.en.md"
            dest_file = PROJECT_ROOT / f"{doc_base_name}.md"

            if not header_file.exists() or not zh_content_file.exists():
                log.warning(
                    f"缺少 {doc_base_name} 的源文件片段，跳过同步。",
                    missing_header=not header_file.exists(),
                    missing_content=not zh_content_file.exists(),
                )
                continue

            header_content = header_file.read_text("utf-8")
            zh_content = zh_content_file.read_text("utf-8")
            en_content = (
                en_content_file.read_text("utf-8") if en_content_file.exists() else ""
            )

            if en_content:
                final_content = (
                    f"{header_content.strip()}\n\n---\n\n"
                    f"<a name='简体中文版'></a>\n{zh_content.strip()}\n\n---\n\n"
                    f"<details>\n<summary><strong>English Version</strong> (Click to expand)</summary>\n\n"
                    f"<a name='english-version'></a>\n{en_content.strip()}\n\n</details>\n"
                )
            else:
                final_content = (
                    f"{header_content.strip()}\n\n---\n\n{zh_content.strip()}"
                )

            log.info(f"正在生成多语言合并文件: {dest_file.name}")
            dest_file.write_text(final_content, "utf-8")

        # 策略 2: 简单同步，只复制主语言并注入链接
        for doc_base_name in SIMPLE_SYNC_FILES:
            source_file = root_zh_dir / f"{doc_base_name}.md"
            dest_file = PROJECT_ROOT / f"{doc_base_name}.md"

            if not source_file.exists():
                continue

            content = source_file.read_text("utf-8")

            en_version_path = (
                DOCS_DIR / "en" / "root_sources" / f"{doc_base_name}.md"
            ).relative_to(PROJECT_ROOT)
            link_header = (
                f'<div align="right">[English Version](./{en_version_path})</div>\n\n'
            )

            final_content = link_header + content

            log.info(f"正在生成单语言同步文件: {dest_file.name}")
            dest_file.write_text(final_content, "utf-8")

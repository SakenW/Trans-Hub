# tools/doc_translator/synchronizer.py
import asyncio
from pathlib import Path
import shutil

import structlog

from trans_hub import Coordinator, TranslationStatus
from .parser import parse_markdown

log = structlog.get_logger()
PROJECT_ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
SOURCE_LANG = "zh"
TARGET_LANGS = ["en"]
# [核心修复] 定义一个合理的并发限制
MAX_CONCURRENT_FILES = 5


class DocSynchronizer:
    def __init__(self, coordinator: Coordinator):
        self.coordinator = coordinator
        # [核心修复] 初始化一个 Semaphore
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_FILES)

    async def run_sync(self):
        """执行完整的文档同步流程。"""
        source_files = list((DOCS_DIR / SOURCE_LANG).rglob("*.md"))
        log.info(f"发现 {len(source_files)} 个源语言 ({SOURCE_LANG}) 文档文件。")
        
        # 1. 并发扫描并登记所有任务 (受信号量限制)
        log.info("\n---> [阶段 1/4] 并发扫描并登记所有任务 <---", concurrency=MAX_CONCURRENT_FILES)
        process_tasks = [self._process_source_file(sf) for sf in source_files]
        await asyncio.gather(*process_tasks)
        
        # 2. 运行 Trans-Hub 后台处理
        log.info("\n---> [阶段 2/4] 开始后台翻译处理 <---")
        for lang in TARGET_LANGS:
            async for _ in self.coordinator.process_pending_translations(lang):
                pass
        log.info("✅ 所有待办任务处理完成。")

        # 3. 并发地重新组装所有目标语言文件
        log.info("\n---> [阶段 3/4] 并发组装目标语言文件 <---", concurrency=MAX_CONCURRENT_FILES)
        assemble_tasks = [self._assemble_target_files(sf) for sf in source_files]
        await asyncio.gather(*assemble_tasks)
        log.info("✅ 所有目标语言文件组装完成。")

        # 4. 同步根目录文件
        log.info("\n---> [阶段 4/4] 同步主语言文档到项目根目录 <---")
        self._sync_root_files()
        log.info("✅ 根目录文档同步完成。")

    async def _process_source_file(self, source_file: Path):
        # [核心修复] 在处理文件之前，先获取信号量
        async with self.semaphore:
            log.debug(f"正在扫描: {source_file.relative_to(PROJECT_ROOT)}")
            content = source_file.read_text("utf-8")
            blocks = parse_markdown(content)
            
            relative_path_str = str(source_file.relative_to(DOCS_DIR / SOURCE_LANG))
            
            for block in blocks:
                business_id = f"docs.{relative_path_str}.{block.stable_id}"
                context = {"category": "technical_documentation", "block_type": block.block_type}
                await self.coordinator.request(
                    target_langs=TARGET_LANGS,
                    text_content=block.source_text,
                    business_id=business_id,
                    context=context,
                )

    async def _assemble_target_files(self, source_file: Path):
        # [核心修复] 同样，在组装文件时也使用信号量
        async with self.semaphore:
            content = source_file.read_text("utf-8")
            blocks = parse_markdown(content)
            
            for lang in TARGET_LANGS:
                log.debug(f"正在组装: {source_file.name} -> {lang}")
                translated_content = content
                
                tasks = [self.coordinator.get_translation(
                    text_content=block.source_text,
                    target_lang=lang,
                    context={"category": "technical_documentation", "block_type": block.block_type}
                ) for block in blocks]
                
                results = await asyncio.gather(*tasks)

                for block, result in zip(blocks, results):
                    if result and result.status == TranslationStatus.TRANSLATED and result.translated_content:
                        translated_content = translated_content.replace(
                            block.source_text, result.translated_content
                        )
                    else:
                        log.warning("未找到翻译，将使用原文。", text=block.source_text[:40]+"...")
                
                relative_path = source_file.relative_to(DOCS_DIR / SOURCE_LANG)
                target_file_path = DOCS_DIR / lang / relative_path
                target_file_path.parent.mkdir(parents=True, exist_ok=True)
                target_file_path.write_text(translated_content, "utf-8")

    def _sync_root_files(self):
        """
        将 docs/zh/root_sources/ 下的源文档复制到项目根目录，
        作为 GitHub 显示的默认文件。
        """
        root_source_dir = DOCS_DIR / SOURCE_LANG / "root_sources"

        if not root_source_dir.is_dir():
            log.warning(
                "未找到 root_sources 目录，跳过根目录同步。", path=str(root_source_dir)
            )
            return

        sync_mapping = {
            "README.md": "README.md",
            "CONTRIBUTING.md": "CONTRIBUTING.md",
            "RELEASE_SOP.md": "RELEASE_SOP.md",
        }

        for source_name, dest_name in sync_mapping.items():
            source_file = root_source_dir / source_name
            if source_file.exists():
                dest_file = PROJECT_ROOT / dest_name
                log.info(
                    "正在同步...",
                    source=source_file.relative_to(PROJECT_ROOT),
                    destination=dest_file.name,
                )
                shutil.copy(source_file, dest_file)
            else:
                log.warning("根目录同步：源文件不存在，跳过。", source=str(source_file))

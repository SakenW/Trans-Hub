# tools/doc_translator/synchronizer.py
"""
负责将解析后的文档结构与 Trans-Hub 核心进行同步。

它的核心职责是：
1. 接收一个 Document 对象。
2. 将 Document 中的所有可翻译块提交给 Trans-Hub。
3. 驱动 Trans-Hub 完成所有待处理的翻译任务。
4. 从 Trans-Hub 拉取翻译结果，并填充回 Document 对象。
"""

import asyncio

import structlog

from trans_hub.coordinator import Coordinator
from trans_hub.engines.base import BaseContextModel
from trans_hub.types import TranslationStatus

from .models import Document, TranslatableBlock

log = structlog.get_logger(__name__)


class DocSyncContext(BaseContextModel):
    """
    用于文档翻译的上下文模型。
    我们将把块的类型 ('paragraph', 'heading', etc.) 作为上下文传递。
    """

    block_type: str


class DocSynchronizer:
    """文档同步器，负责与 Trans-Hub 的所有交互。"""

    def __init__(self, coordinator: Coordinator):
        self.coordinator = coordinator

    async def dispatch_document_to_trans_hub(self, doc: Document) -> None:
        """将单个文档中的所有可翻译块提交给 Trans-Hub。"""
        log.info(
            "正在分发文档翻译任务...",
            document=doc.source_path.name,
            block_count=len(doc.blocks),
        )
        tasks = []
        for block in doc.blocks:
            # 我们只翻译 node_type 不是 'block_code' 的块
            if block.node_type != "block_code":
                task = self.coordinator.request(
                    target_langs=doc.target_langs,
                    text_content=block.source_text,
                    business_id=block.business_id,
                    source_lang=doc.source_lang,
                    context=DocSyncContext(block_type=block.node_type).model_dump(),
                )
                tasks.append(task)

        # 并发提交所有请求
        await asyncio.gather(*tasks)
        log.info("文档任务分发完成", document=doc.source_path.name)

    async def process_all_pending(self, target_langs: list[str]) -> None:
        """处理所有指定目标语言的待翻译任务。"""
        for lang in target_langs:
            log.info(f"▶️ 开始处理 [{lang}] 的待翻译任务...")
            processed_count = 0
            try:
                async for result in self.coordinator.process_pending_translations(lang):
                    processed_count += 1
                    if result.status == TranslationStatus.TRANSLATED:
                        log.debug(
                            "  - 翻译成功",
                            lang=lang,
                            original=result.original_content[:30] + "...",
                        )
                    else:
                        log.warning(
                            "  - 翻译失败",
                            lang=lang,
                            original=result.original_content[:30] + "...",
                            error=result.error,
                        )
                log.info(
                    f"✅ 完成 [{lang}] 的翻译处理", processed_count=processed_count
                )
            except Exception:
                log.error("处理待办任务时发生严重错误", lang=lang, exc_info=True)

    async def fetch_translations_for_document(self, doc: Document) -> None:
        """为单个文档中的所有块，从 Trans-Hub 获取已完成的翻译并填充回去。"""
        log.info("正在为文档获取翻译结果...", document=doc.source_path.name)

        async def fetch_for_block(block: TranslatableBlock):
            """内部辅助函数，用于并发获取单个块的所有语言翻译。"""
            if block.node_type == "block_code":
                # 代码块无需翻译，直接用原文填充所有目标语言
                for lang in doc.target_langs:
                    block.add_translation(lang, block.source_text)
                return

            for lang in doc.target_langs:
                result = await self.coordinator.get_translation(
                    text_content=block.source_text,
                    target_lang=lang,
                    context=DocSyncContext(block_type=block.node_type).model_dump(),
                )
                if (
                    result
                    and result.status == TranslationStatus.TRANSLATED
                    and result.translated_content
                ):
                    block.add_translation(lang, result.translated_content)
                else:
                    # 如果没有翻译，使用原文作为占位符
                    log.warning(
                        "未找到翻译，将使用原文作为占位符",
                        lang=lang,
                        business_id=block.business_id,
                    )
                    block.add_translation(lang, block.source_text)

        # 并发获取所有块的翻译
        await asyncio.gather(*(fetch_for_block(block) for block in doc.blocks))
        log.info("文档翻译结果获取完成", document=doc.source_path.name)

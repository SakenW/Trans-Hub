"""
trans_hub/coordinator.py (v0.1)

本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。
它是上层应用与 Trans-Hub 核心功能交互的主要入口点。
"""
import logging
from typing import Dict, Generator, List, Optional, Type

from trans_hub.utils import get_context_hash

from trans_hub.engines.base import BaseTranslationEngine
from trans_hub.interfaces import PersistenceHandler
from trans_hub.types import (
    ContentItem,
    EngineBatchItemResult,
    EngineError,
    EngineSuccess,
    TranslationResult,
    TranslationStatus,
)

# 获取一个模块级别的日志记录器
logger = logging.getLogger(__name__)


class Coordinator:
    """
    同步版本的主协调器。

    职责:
    - 持有并协调核心组件（持久化处理器、翻译引擎）。
    - 编排核心工作流，如处理待办翻译任务。
    - 执行校验和策略（未来将包括重试、限速等）。
    """

    def __init__(
        self,
        persistence_handler: PersistenceHandler,
        engines: Dict[str, BaseTranslationEngine],
        active_engine_name: str,
    ):
        """
        初始化协调器。

        采用依赖注入模式，将所有外部依赖作为参数传入。

        Args:
            persistence_handler: 一个实现了 PersistenceHandler 接口的实例。
            engines: 一个字典，映射了引擎名称到已初始化的引擎实例。
            active_engine_name: 当前要使用的活动引擎的名称。
        """
        self.handler = persistence_handler
        self.engines = engines
        
        # 检查活动引擎是否存在并设置
        if active_engine_name not in self.engines:
            raise ValueError(
                f"指定的活动引擎 '{active_engine_name}' 不在已提供的引擎列表中: "
                f"{list(self.engines.keys())}"
            )
        self.active_engine = self.engines[active_engine_name]
        self.active_engine_name = active_engine_name
        
        logger.info(
            f"Coordinator 初始化完成。活动引擎: '{self.active_engine_name}'"
        )

    def process_pending_translations(
        self,
        target_lang: str,
        batch_size: int = 50,
        limit: Optional[int] = None,
    ) -> Generator[TranslationResult, None, None]:
        """
        处理指定语言的待翻译任务。

        这是一个生成器函数，它会流式地处理任务并立即返回结果，
        同时在后台异步（在同步版本中是并发）保存结果。

        工作流:
        1. 从持久化层流式获取待翻译的内容批次 (`ContentItem`)。
           在获取时，这些任务的状态在数据库中已被原子地更新为 'TRANSLATING'。
        2. 将每个批次发送给当前的活动翻译引擎。
        3. 对引擎返回的结果进行处理和转换。
        4. **立即 `yield`** 一个 `TranslationResult` 对象给调用者。
        5. 将处理后的结果批量保存回持久化层。

        Args:
            target_lang: 要处理的目标语言代码。
            batch_size: 每次从数据库获取和发送给引擎的批次大小。
            limit: 本次调用处理的总任务数上限。

        Yields:
            一个 `TranslationResult` 对象，代表一个翻译任务的处理结果。
        """
        logger.info(
            f"开始处理 '{target_lang}' 的待翻译任务 (batch_size={batch_size}, limit={limit})"
        )
        
        # 从数据库流式获取任务批次
        content_batches = self.handler.stream_translatable_items(
            lang_code=target_lang,
            statuses=[TranslationStatus.PENDING, TranslationStatus.FAILED], # 也可以处理失败后待重试的任务
            batch_size=batch_size,
            limit=limit,
        )

        for batch in content_batches:
            logger.debug(f"正在处理一个包含 {len(batch)} 个内容的批次。")
            
            # 提取纯文本列表以发送给引擎
            texts_to_translate = [item.value for item in batch]
            
            try:
                # 调用翻译引擎
                engine_results = self.active_engine.translate_batch(
                    texts=texts_to_translate,
                    target_lang=target_lang,
                    # 此处暂不传递 context，未来可以从 batch item 中获取
                )
            except Exception as e:
                # 如果引擎的 translate_batch 方法本身抛出异常，则整个批次都失败
                logger.error(
                    f"引擎 '{self.active_engine_name}' 在处理批次时抛出异常: {e}",
                    exc_info=True
                )
                # 为批次中的每个项目创建一个失败的 TranslationResult
                engine_results = [
                    EngineError(error_message=str(e), is_retryable=True)
                ] * len(batch)

            # 将引擎结果和原始任务进行匹配和转换
            final_results_to_save: List[TranslationResult] = []
            for item, engine_result in zip(batch, engine_results):
                result = self._convert_to_translation_result(
                    item=item,
                    engine_result=engine_result,
                    target_lang=target_lang,
                )
                final_results_to_save.append(result)
                yield result  # 立即将结果返回给调用者

            # 批处理结束后，将这一批的最终结果保存到数据库
            if final_results_to_save:
                self.handler.save_translations(final_results_to_save)
                logger.debug(f"已将 {len(final_results_to_save)} 条结果提交给持久化层保存。")

    def _convert_to_translation_result(
        self,
        item: ContentItem,
        engine_result: EngineBatchItemResult,
        target_lang: str,
    ) -> TranslationResult:
        """
        一个内部辅助方法，用于将引擎的原始输出转换为统一的 `TranslationResult` DTO。
        """
        if isinstance(engine_result, EngineSuccess):
            return TranslationResult(
                original_content=item.value,
                translated_content=engine_result.translated_text,
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                engine=self.active_engine_name,
                from_cache=False, # 假设此时非缓存，缓存逻辑应在更高层处理
                context_hash=item.context_hash,
            )
        elif isinstance(engine_result, EngineError):
            # 在 v0.1 中，我们简单地将所有引擎错误标记为 FAILED。
            # 在未来的版本中，可以根据 `is_retryable` 实现重试逻辑。
            return TranslationResult(
                original_content=item.value,
                translated_content=None,
                target_lang=target_lang,
                status=TranslationStatus.FAILED,
                engine=self.active_engine_name,
                error=engine_result.error_message,
                from_cache=False,
                context_hash=item.context_hash,
            )
        else:
            # 这是一个防御性编程，防止引擎返回了未知的类型。
            raise TypeError(f"未知的引擎结果类型: {type(engine_result)}")


    def request(
        self,
        target_langs: List[str],
        text_content: str,
        business_id: Optional[str] = None,
        context: Optional[dict] = None,
        source_lang: Optional[str] = None,
    ) -> None:
        """
        统一的翻译请求入口。

        此方法负责登记一个翻译需求。它会创建或更新源记录，
        并为每种目标语言创建状态为 'PENDING' 的翻译任务（如果尚不存在）。
        这是一个幂等操作。

        Args:
            target_langs: 一个目标语言代码的列表，例如 ['en', 'de', 'jp']。
            text_content: 需要翻译的文本内容。
            business_id: 业务唯一ID，可选。
            context: 引擎特定的上下文信息，可选。
            source_lang: 源语言代码，可选。
        """
        logger.debug(
            f"收到翻译请求: business_id='{business_id}', "
            f"langs={target_langs}, content='{text_content[:30]}...'"
        )

        # 1. 根据上下文生成哈希
        context_hash = get_context_hash(context)

        # 2. 更新或创建源记录
        # 注意：在 "纯文本" 模式 (business_id=None) 下，我们不操作 th_sources 表。
        content_id = None
        if business_id:
            source_result = self.handler.update_or_create_source(
                text_content=text_content,
                business_id=business_id,
                context_hash=context_hash,
            )
            content_id = source_result.content_id
        
        # 3. 为每种目标语言创建 PENDING 任务
        # 这是一个 "INSERT OR IGNORE" 逻辑，如果记录已存在，则什么都不做。
        with self.handler.transaction() as cursor:
            # 如果没有 business_id，我们需要先找到或创建 content 记录
            if not content_id:
                cursor.execute("SELECT id FROM th_content WHERE value = ?", (text_content,))
                row = cursor.fetchone()
                if row:
                    content_id = row['id']
                else:
                    cursor.execute("INSERT INTO th_content (value) VALUES (?)", (text_content,))
                    content_id = cursor.lastrowid

            # 准备批量插入
            insert_sql = """
                INSERT OR IGNORE INTO th_translations 
                (content_id, lang_code, context_hash, status, source_lang_code, engine_version)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            
            params_to_insert = [
                (
                    content_id,
                    lang,
                    context_hash,
                    TranslationStatus.PENDING.value,
                    source_lang,
                    self.active_engine.VERSION, # 使用活动引擎的版本
                )
                for lang in target_langs
            ]
            
            cursor.executemany(insert_sql, params_to_insert)
            logger.info(
                f"为 content_id={content_id} 确保了 {cursor.rowcount} 个新的 PENDING 任务。"
            )

    def close(self):
        """关闭协调器及其持有的资源，主要是数据库连接。"""
        logger.info("正在关闭 Coordinator...")
        self.handler.close()
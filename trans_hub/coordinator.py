"""
trans_hub/coordinator.py (v0.1)

本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。
它是上层应用与 Trans-Hub 核心功能交互的主要入口点。
"""
import time
import logging
from typing import Dict, Generator, List, Optional, Type
from trans_hub.rate_limiter import RateLimiter
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

# ... 在 Coordinator 类中 ...

    def __init__(
        self,
        persistence_handler: PersistenceHandler,
        engines: Dict[str, BaseTranslationEngine],
        active_engine_name: str,
        # [新] 增加速率限制器作为可选依赖
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """
        [v0.3] 初始化协调器，增加了对速率限制器的支持。
        """
        self.handler = persistence_handler
        self.engines = engines
        # [新] 保存速率限制器实例
        self.rate_limiter = rate_limiter
        
        if active_engine_name not in self.engines:
            raise ValueError(
                f"指定的活动引擎 '{active_engine_name}' 不在已提供的引擎列表中: "
                f"{list(self.engines.keys())}"
            )
        self.active_engine = self.engines[active_engine_name]
        self.active_engine_name = active_engine_name
        
        logger.info(
            f"Coordinator 初始化完成。活动引擎: '{self.active_engine_name}', "
            f"速率限制器: {'已启用' if self.rate_limiter else '未启用'}"
        )

    def process_pending_translations(
        self,
        target_lang: str,
        batch_size: int = 50,
        limit: Optional[int] = None,
        # [新] 为重试策略添加参数
        max_retries: int = 2,       # 最多重试2次 (总共尝试3次)
        initial_backoff: float = 1.0, # 初始退避时间1秒
    ) -> Generator[TranslationResult, None, None]:
        """
        [v0.2] 处理指定语言的待翻译任务，增加了重试逻辑。
        """
        logger.info(
            f"开始处理 '{target_lang}' 的待翻译任务 (max_retries={max_retries})"
        )
        
        content_batches = self.handler.stream_translatable_items(
            lang_code=target_lang,
            statuses=[TranslationStatus.PENDING, TranslationStatus.FAILED],
            batch_size=batch_size,
            limit=limit,
        )

        for batch in content_batches:
            logger.debug(f"正在处理一个包含 {len(batch)} 个内容的批次。")
            texts_to_translate = [item.value for item in batch]
            
            # --- [新] 重试循环 ---
            engine_results: List[EngineBatchItemResult] = []
            for attempt in range(max_retries + 1):
                try:
                    # --- [新] 在调用引擎前获取令牌 ---
                    if self.rate_limiter:
                        logger.debug("正在等待速率限制器...")
                        # 每次 API 调用被视为消耗一个令牌
                        self.rate_limiter.acquire(1)
                        logger.debug("已获取速率限制器令牌，继续执行。")
                    # --- 速率限制结束 ---
                    
                    engine_results = self.active_engine.translate_batch(
                        texts=texts_to_translate,
                        target_lang=target_lang,
                    )
                    
                    # 检查批次中是否还有可重试的错误
                    has_retryable_errors = any(
                        isinstance(r, EngineError) and r.is_retryable for r in engine_results
                    )

                    if not has_retryable_errors:
                        # 如果没有可重试的错误，说明批次成功或遇到了不可重试的错误，跳出重试循环
                        logger.info(f"批次处理成功或遇到不可重试错误 (尝试次数: {attempt + 1})。")
                        break
                    
                    # 如果还有可重试的错误，记录日志并准备下一次重试
                    logger.warning(
                        f"批次中包含可重试的错误 (尝试次数: {attempt + 1}/{max_retries + 1})。"
                        "将在退避后重试..."
                    )

                except Exception as e:
                    logger.error(
                        f"引擎在处理批次时抛出异常 (尝试次数: {attempt + 1}): {e}",
                        exc_info=True
                    )
                    engine_results = [EngineError(error_message=str(e), is_retryable=True)] * len(batch)

                # 如果不是最后一次尝试，则进行指数退避等待
                if attempt < max_retries:
                    backoff_time = initial_backoff * (2 ** attempt)
                    logger.info(f"退避 {backoff_time:.2f} 秒...")
                    time.sleep(backoff_time)
                else:
                    logger.error(f"已达到最大重试次数 ({max_retries})，放弃重试。")
            # --- 重试循环结束 ---

            final_results_to_save: List[TranslationResult] = []
            for item, engine_result in zip(batch, engine_results):
                result = self._convert_to_translation_result(
                    item=item,
                    engine_result=engine_result,
                    target_lang=target_lang,
                )
                final_results_to_save.append(result)
                yield result

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
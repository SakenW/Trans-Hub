# trans_hub/coordinator.py

"""
本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。

它采用动态引擎发现机制，并负责编排所有核心工作流，包括任务处理、重试、
速率限制、请求处理和垃圾回收等。
"""

import asyncio
import json
import re
from collections.abc import Generator, AsyncGenerator
from typing import Any, Optional

import structlog
from trans_hub.cache import TranslationCache

from trans_hub.config import TransHubConfig
from trans_hub.types import TranslationRequest
from trans_hub.engine_registry import ENGINE_REGISTRY
from trans_hub.engines.base import BaseTranslationEngine
from trans_hub.interfaces import PersistenceHandler
from trans_hub.rate_limiter import RateLimiter
from trans_hub.types import (
    ContentItem,
    EngineBatchItemResult,
    EngineError,
    EngineSuccess,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.utils import get_context_hash

# 获取一个 logger
logger = structlog.get_logger(__name__)


class Coordinator:
    """同步版本的主协调器。
    实现了动态引擎加载、重试、速率限制等所有核心功能。
    v1.1.1: 增加了对纯异步引擎的“异步感知”支持，并修复了上下文传递问题。
    """

    def __init__(
        self,
        config: TransHubConfig,
        persistence_handler: PersistenceHandler,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        """初始化协调器。"""
        self.config = config
        self.cache = TranslationCache(self.config.cache_config)
        self.handler = persistence_handler
        self.active_engine_name = config.active_engine
        self.rate_limiter = rate_limiter

        logger.info(
            "正在初始化 Coordinator...", available_engines=list(ENGINE_REGISTRY.keys())
        )

        if self.active_engine_name not in ENGINE_REGISTRY:
            raise ValueError(
                f"指定的活动引擎 '{self.active_engine_name}' 不可用。"
                f"可能原因：1. 引擎不存在；2. 缺少相关依赖（如 'openai' 或 'translators'）。"
                f"当前可用引擎: {list(ENGINE_REGISTRY.keys())}"
            )

        engine_class = ENGINE_REGISTRY[self.active_engine_name]

        engine_config_data = getattr(
            config.engine_configs, self.active_engine_name, None
        )
        if not engine_config_data:
            raise ValueError(
                f"在配置中未找到活动引擎 '{self.active_engine_name}' 的配置。"
            )

        # 实例化引擎配置
        engine_config_instance = engine_class.CONFIG_MODEL(
            **engine_config_data.model_dump()
        )

        # 实例化活动引擎
        self.active_engine: BaseTranslationEngine[Any] = engine_class(
            config=engine_config_instance
        )

        # 核心修补: 在初始化时检查源语言依赖
        if self.active_engine.REQUIRES_SOURCE_LANG and not self.config.source_lang:
            raise ValueError(
                f"活动引擎 '{self.active_engine_name}' 需要提供源语言 (REQUIRES_SOURCE_LANG=True), "
                f"但全局配置 'source_lang' 未设置。"
            )

        # 初始化异步引擎的事件循环
        self.loop = None
        if self.active_engine.IS_ASYNC_ONLY:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

        logger.info(
            f"Coordinator 初始化完成。活动引擎: '{self.active_engine_name}', "
            f"速率限制器: {'已启用' if self.rate_limiter else '未启用'}"
        )

    async def process_pending_translations(
        self,
        target_lang: str,
        batch_size: Optional[int] = None,
        limit: Optional[int] = None,
        max_retries: Optional[int] = None,
        initial_backoff: Optional[float] = None,
    ) -> AsyncGenerator[TranslationResult, None]:
        """处理指定语言的待翻译任务，内置重试和速率限制逻辑。"""
        self._validate_lang_codes([target_lang])

        # 如果未提供参数，则从配置中获取默认值
        # 动态调整批次大小以适应引擎能力
        engine_batch_size = getattr(self.active_engine, 'MAX_BATCH_SIZE', self.config.batch_size)
        batch_size = batch_size if batch_size is not None else min(self.config.batch_size, engine_batch_size)
        max_retries = (
            max_retries
            if max_retries is not None
            else self.config.retry_policy.max_attempts
        )
        initial_backoff = (
            initial_backoff
            if initial_backoff is not None
            else self.config.retry_policy.initial_backoff
        )

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
            if not batch:
                continue

            logger.debug(f"正在处理一个包含 {len(batch)} 个内容的批次。")
            texts_to_translate = [item.value for item in batch]

            # 定义 batch_results，确保其在循环中始终可用
            batch_results: list[EngineBatchItemResult] = []

            context_dict = batch[0].context
            validated_context = None
            if context_dict and self.active_engine.CONTEXT_MODEL:
                try:
                    validated_context = self.active_engine.CONTEXT_MODEL.model_validate(
                        context_dict
                    )
                except Exception as e:
                    logger.error(
                        "上下文验证失败，将作为错误处理整个批次",
                        context=context_dict,
                        error=str(e),
                        exc_info=True,
                    )
                    # 如果上下文验证失败，直接生成错误结果并跳过API调用
                    batch_results = [
                        EngineError(
                            error_message=f"无效的上下文: {e}", is_retryable=False
                        )
                    ] * len(batch)
                    async for result in self._process_and_save_batch_results(
                        batch, batch_results, target_lang
                    ):
                        yield result
                    continue

            for attempt in range(max_retries + 1):
                try:
                    # 检查缓存
                    batch_results = []
                    uncached_texts = []
                    uncached_indices = []
                    for i, item in enumerate(batch):
                        cached_result = await self.cache.get_cached_result(
                            TranslationRequest(
                                source_text=item.value,
                                source_lang=self.config.source_lang,
                                target_lang=target_lang,
                                context_hash=item.context_hash
                            )
                        )
                        if cached_result:
                            batch_results.append(EngineSuccess(translated_text=cached_result, from_cache=True))
                        else:
                            uncached_texts.append(item.value)
                            uncached_indices.append(i)
                except Exception as e:
                    logger.error(f"缓存处理异常: {str(e)}")
                    # 回退到无缓存处理
                    batch_results = await self._process_uncached_batch(batch, target_lang)

                if uncached_texts:
                    if self.rate_limiter:
                        await self.rate_limiter.acquire(1)

                    if self.active_engine.IS_ASYNC_ONLY:
                        logger.debug(
                            "调用纯异步引擎...", engine=self.active_engine_name
                        )
                        uncached_results = await self.active_engine.atranslate_batch(
                            texts=uncached_texts,
                            target_lang=target_lang,
                            source_lang=self.config.source_lang,
                            context=validated_context,
                        )
                    else:
                        logger.debug("调用同步引擎...", engine=self.active_engine_name)
                        uncached_results = self.active_engine.translate_batch(
                            texts=uncached_texts,
                            target_lang=target_lang,
                            source_lang=self.config.source_lang,
                            context=validated_context,
                        )

                    # 合并未缓存结果到批次结果中
                    try:
                        for idx, result in zip(uncached_indices, uncached_results):
                            batch_results.insert(idx, result)
                    except Exception as e:
                        logger.error(f"缓存批次处理失败: {str(e)}")
                        raise

                    # 缓存新翻译结果
                    try:
                        for item, result in zip([batch[i] for i in uncached_indices], uncached_results):
                            if isinstance(result, EngineSuccess):
                                await self.cache.cache_translation_result(
                                    TranslationRequest(
                                        source_text=item.value,
                                        source_lang=self.config.source_lang,
                                        target_lang=target_lang,
                                        context_hash=item.context_hash
                                    ),
                                    result.translated_text
                                )
                    except Exception as e:
                        logger.error(f"缓存处理过程中发生错误: {str(e)}")
                        # 使用原始批次处理逻辑作为回退
                        batch_results = await self._process_uncached_batch(batch, target_lang)

                # --- 统一的重试判断逻辑 ---
                # 在每次尝试后，检查整个批次是否存在可重试的错误
                has_retryable_errors = any(
                    isinstance(r, EngineError) and r.is_retryable for r in batch_results
                )

                if not has_retryable_errors:
                    logger.info(f"批次处理成功或仅包含不可重试错误 (尝试次数: {attempt + 1})。")
                    break  # 成功，或遇到不可重试的错误，直接跳出重试循环

                # 如果运行到这里，说明需要重试
                if attempt < max_retries:
                    backoff_time = initial_backoff * (2**attempt)
                    logger.warning(
                        f"批次中包含可重试的错误，将在 {backoff_time:.2f} 秒后重试 (尝试次数: {attempt + 1}/{max_retries + 1})."
                    )
                    await asyncio.sleep(backoff_time)
                else:
                    logger.error(
                        f"批次处理达到最大重试次数 ({max_retries + 1})，将保留当前失败状态。"
                    )

            async for result in self._process_and_save_batch_results(
                batch, batch_results, target_lang
            ):
                yield result

    async def _process_uncached_batch(self, batch: list[ContentItem], target_lang: str) -> list[EngineBatchItemResult]:
        """处理未缓存的批次翻译请求"""
        try:
            if self.active_engine.IS_ASYNC_ONLY:
                results = await self.active_engine.atranslate_batch(
                    texts=[item.value for item in batch],
                    target_lang=target_lang,
                    source_lang=self.config.source_lang,
                    context=self._get_batch_context(batch)
                )
            else:
                results = self.active_engine.translate_batch(
                    texts=[item.value for item in batch],
                    target_lang=target_lang,
                    source_lang=self.config.source_lang,
                    context=self._get_batch_context(batch)
                )
            return results
        except Exception as e:
            logger.error(f"处理未缓存批次时发生错误: {str(e)}", exc_info=True)
            return [EngineError(error_message=str(e), is_retryable=True)] * len(batch)

    def _get_batch_context(self, batch: list[ContentItem]) -> Optional[dict]:
        """获取批次的上下文信息"""
        if batch and batch[0].context_hash:
            return self.handler.get_context_by_hash(batch[0].context_hash)
        return None

    async def _process_and_save_batch_results(
        self,
        batch: list[ContentItem],
        engine_results: list[EngineBatchItemResult],
        target_lang: str,
    ) -> Generator[TranslationResult, None, None]:
        """内部辅助方法，将引擎结果转换为 DTO，保存到数据库，并逐个返回。"""
        final_results_to_save: list[TranslationResult] = []
        for item, engine_result in zip(batch, engine_results):
            retrieved_business_id = self.handler.get_business_id_for_content(
                content_id=item.content_id, context_hash=item.context_hash
            )

            if retrieved_business_id:
                self.handler.touch_source(retrieved_business_id)

            result = self._convert_to_translation_result(
                item=item,
                engine_result=engine_result,
                target_lang=target_lang,
                retrieved_business_id=retrieved_business_id,
            )
            final_results_to_save.append(result)

            yield result

        if final_results_to_save:
            self.handler.save_translations(final_results_to_save)

    def _convert_to_translation_result(
        self,
        item: ContentItem,
        engine_result: EngineBatchItemResult,
        target_lang: str,
        retrieved_business_id: Optional[str] = None,
    ) -> TranslationResult:
        """内部辅助方法，将引擎原始输出转换为统一的 TranslationResult DTO。"""
        if isinstance(engine_result, EngineSuccess):
            return TranslationResult(
                original_content=item.value,
                translated_content=engine_result.translated_text,
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                engine=self.active_engine_name,
                from_cache=engine_result.from_cache,
                context_hash=item.context_hash,
                business_id=retrieved_business_id,
            )
        elif isinstance(engine_result, EngineError):
            return TranslationResult(
                original_content=item.value,
                translated_content=None,
                target_lang=target_lang,
                status=TranslationStatus.FAILED,
                engine=self.active_engine_name,
                error=engine_result.error_message,
                from_cache=False,
                context_hash=item.context_hash,
                business_id=retrieved_business_id,
            )
        else:
            raise TypeError(
                f"未知的引擎结果类型: {type(engine_result)}。预期 EngineSuccess 或 EngineError。"
            )

    def request(
        self,
        target_langs: list[str],
        text_content: str,
        business_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """统一的翻译请求入口。"""
        self._validate_lang_codes(target_langs)

        logger.debug(
            "收到翻译请求",
            business_id=business_id,
            target_langs=target_langs,
            text_content=text_content[:30] + "...",
        )
        context_hash = get_context_hash(context)
        # 核心修复: 将 context 字典序列化为 JSON 字符串，以便存入数据库
        context_json = json.dumps(context) if context else None
        content_id: Optional[int] = None

        if business_id:
            source_result = self.handler.update_or_create_source(
                text_content=text_content,
                business_id=business_id,
                context_hash=context_hash,
            )
            content_id = source_result.content_id

        with self.handler.transaction() as cursor:
            if content_id is None:
                # 首先尝试查找现有的 content_id
                cursor.execute(
                    "SELECT id FROM th_content WHERE value = ?", (text_content,)
                )
                row = cursor.fetchone()
                if row:
                    content_id = row["id"]
                else:
                    # 如果不存在，则插入新的内容
                    cursor.execute(
                        "INSERT INTO th_content (value) VALUES (?)", (text_content,)
                    )
                    content_id = cursor.lastrowid

            if content_id is None:
                raise RuntimeError("无法为翻译任务确定 content_id。")

            # 核心修复: 在 INSERT 语句中加入 context 列
            insert_sql = """
                INSERT OR IGNORE INTO th_translations
                (content_id, lang_code, context_hash, status, source_lang_code, engine_version, context)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            params_to_insert = []
            for lang in target_langs:
                cursor.execute(
                    "SELECT status FROM th_translations WHERE content_id = ? AND lang_code = ? AND context_hash = ?",
                    (content_id, lang, context_hash),
                )
                existing_translation = cursor.fetchone()

                if (
                    existing_translation
                    and existing_translation["status"]
                    == TranslationStatus.TRANSLATED.value
                ):
                    continue

                # 核心修复: 在参数元组中添加 context_json
                params_to_insert.append(
                    (
                        content_id,
                        lang,
                        context_hash,
                        TranslationStatus.PENDING.value,
                        self.config.source_lang,  # <-- 使用全局配置
                        self.active_engine.VERSION,
                        context_json,
                    )
                )

            if params_to_insert:
                cursor.executemany(insert_sql, params_to_insert)
                logger.info(
                    f"为 content_id={content_id} 确保了 {cursor.rowcount} 个新的 PENDING 任务。"
                )

    def run_garbage_collection(
        self, retention_days: Optional[int] = None, dry_run: bool = False
    ) -> dict:
        """运行垃圾回收进程。"""
        if retention_days is None:
            retention_days = self.config.gc_retention_days

        logger.info(
            f"Coordinator 正在启动垃圾回收 (retention_days={retention_days}, dry_run={dry_run})..."
        )
        return self.handler.garbage_collect(
            retention_days=retention_days, dry_run=dry_run
        )

    def _validate_lang_codes(self, lang_codes: list[str]):
        """内部辅助方法：校验语言代码列表中的每个代码是否符合标准格式。"""
        lang_code_pattern = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")

        for code in lang_codes:
            if not lang_code_pattern.match(code):
                raise ValueError(
                    f"提供的语言代码 '{code}' 格式无效。 "
                    "请使用标准格式，例如 'en', 'de', 'zh-CN'。"
                )

    def close(self):
        """关闭协调器及其持有的资源。"""
        logger.info("正在关闭 Coordinator...")
        self.handler.close()
        if self.loop is not None:
            self.loop.close()

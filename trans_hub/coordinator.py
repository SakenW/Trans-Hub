"""trans_hub/coordinator.py (v1.0 Final - 最终最终修正版)

本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。
它采用动态引擎发现机制，并负责编排所有核心工作流，包括任务处理、重试、
速率限制、请求处理和垃圾回收等。
"""

import re
import time
from typing import Any, Dict, Generator, List, Optional

import structlog

from trans_hub.config import TransHubConfig

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
from trans_hub.utils import get_context_hash # get_context_hash 现在返回 str

logger = structlog.get_logger(__name__)


class Coordinator:
    """同步版本的主协调器。
    实现了动态引擎加载、重试、速率限制等所有核心功能。
    """

    def __init__(
        self,
        config: TransHubConfig,
        persistence_handler: PersistenceHandler,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """初始化协调器。"""
        self.config = config
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
            raise ValueError(f"在配置中未找到活动引擎 '{self.active_engine_name}' 的配置。")

        engine_config_instance = engine_class.CONFIG_MODEL(
            **engine_config_data.model_dump()
        )

        self.active_engine: BaseTranslationEngine[Any] = engine_class(
            config=engine_config_instance
        )
        logger.info(
            f"Coordinator 初始化完成。活动引擎: '{self.active_engine_name}', "
            f"速率限制器: {'已启用' if self.rate_limiter else '未启用'}"
        )

    def process_pending_translations(
        self,
        target_lang: str,
        batch_size: int = 50,
        limit: Optional[int] = None,
        max_retries: int = 2,
        initial_backoff: float = 1.0,
    ) -> Generator[TranslationResult, None, None]:
        """处理指定语言的待翻译任务，内置重试和速率限制逻辑。"""
        self._validate_lang_codes([target_lang])

        logger.info(f"开始处理 '{target_lang}' 的待翻译任务 (max_retries={max_retries})")

        # stream_translatable_items 返回 ContentItem，不包含 business_id
        content_batches = self.handler.stream_translatable_items(
            lang_code=target_lang,
            statuses=[TranslationStatus.PENDING, TranslationStatus.FAILED],
            batch_size=batch_size,
            limit=limit,
        )

        for batch in content_batches:
            logger.debug(f"正在处理一个包含 {len(batch)} 个内容的批次。")
            texts_to_translate = [item.value for item in batch]

            engine_results: List[EngineBatchItemResult] = []
            for attempt in range(max_retries + 1):
                try:
                    if self.rate_limiter:
                        logger.debug("正在等待速率限制器令牌...")
                        self.rate_limiter.acquire(1)
                        logger.debug("已获取速率限制器令牌，继续执行翻译。")

                    engine_results = self.active_engine.translate_batch(
                        texts=texts_to_translate,
                        target_lang=target_lang,
                    )

                    has_retryable_errors = any(
                        isinstance(r, EngineError) and r.is_retryable
                        for r in engine_results
                    )

                    if not has_retryable_errors:
                        logger.info(f"批次处理成功或仅包含不可重试错误 (尝试次数: {attempt + 1})。")
                        break

                    logger.warning(
                        f"批次中包含可重试的错误 (尝试次数: {attempt + 1}/{max_retries + 1})。"
                        "将在退避后重试批次..."
                    )

                except Exception as e:
                    logger.error(
                        f"引擎在处理批次时抛出异常 (尝试次数: {attempt + 1})",
                        exc_info=True,
                    )
                    engine_results = [
                        EngineError(error_message=str(e), is_retryable=True)
                    ] * len(batch)

                if attempt < max_retries:
                    backoff_time = initial_backoff * (2**attempt)
                    logger.info(f"退避 {backoff_time:.2f} 秒后重试...")
                    time.sleep(backoff_time)
                else:
                    logger.error(f"已达到最大重试次数 ({max_retries})，放弃当前批次的重试。")

            final_results_to_save: List[TranslationResult] = []
            for item, engine_result in zip(batch, engine_results):
                # 核心修改：在转换为 TranslationResult 时，从 persistence_handler 动态获取 business_id
                retrieved_business_id = self.handler.get_business_id_for_content(
                    content_id=item.content_id, context_hash=item.context_hash
                )

                result = self._convert_to_translation_result(
                    item=item,
                    engine_result=engine_result,
                    target_lang=target_lang,
                    retrieved_business_id=retrieved_business_id # <-- 传递获取到的 business_id
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
        retrieved_business_id: Optional[str] = None # <-- 新增参数
    ) -> TranslationResult:
        """内部辅助方法，将引擎原始输出转换为统一的 TranslationResult DTO。
        现在接受一个可选的 retrieved_business_id。
        """
        if isinstance(engine_result, EngineSuccess):
            return TranslationResult(
                original_content=item.value,
                translated_content=engine_result.translated_text,
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                engine=self.active_engine_name,
                from_cache=False,
                context_hash=item.context_hash,
                business_id=retrieved_business_id, # <-- 使用传递进来的 business_id
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
                business_id=retrieved_business_id, # <-- 使用传递进来的 business_id
            )
        else:
            raise TypeError(
                f"未知的引擎结果类型: {type(engine_result)}。预期 EngineSuccess 或 EngineError。"
            )

    def request(
        self,
        target_langs: List[str],
        text_content: str,
        business_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        source_lang: Optional[str] = None,
    ) -> None:
        """统一的翻译请求入口。
        负责根据传入的文本和目标语言，创建或更新源记录，并生成待翻译任务。
        """
        self._validate_lang_codes(target_langs)
        if source_lang:
            self._validate_lang_codes([source_lang])

        logger.debug(
            f"收到翻译请求: business_id='{business_id}', "
            f"目标语言={target_langs}, 内容='{text_content[:30]}...'"
        )
        context_hash = get_context_hash(context)
        content_id: Optional[int] = None

        # 如果提供了 business_id，则先更新或创建源记录 (th_sources)
        if business_id:
            source_result = self.handler.update_or_create_source(
                text_content=text_content,
                business_id=business_id,
                context_hash=context_hash,
            )
            content_id = source_result.content_id
        
        # 无论 business_id 是否提供，都需要确保 content 存在
        # 如果没有通过 business_id 找到 content_id (即 business_id 为 None)，
        # 则尝试根据文本内容查找或插入
        with self.handler.transaction() as cursor:
            if content_id is None:
                cursor.execute(
                    "SELECT id FROM th_content WHERE value = ?", (text_content,)
                )
                row = cursor.fetchone()
                if row:
                    content_id = row["id"]
                else:
                    cursor.execute(
                        "INSERT INTO th_content (value) VALUES (?)", (text_content,)
                    )
                    content_id = cursor.lastrowid

            if content_id is None:
                raise RuntimeError(
                    "Failed to determine content_id for translation task."
                )

            # 插入或忽略新的翻译任务
            # 不再在 th_translations 中存储 business_id
            insert_sql = """
                INSERT OR IGNORE INTO th_translations
                (content_id, lang_code, context_hash, status, source_lang_code, engine_version)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            params_to_insert = []
            for lang in target_langs:
                # 检查是否已存在 TRANSLATED 状态的翻译
                cursor.execute(
                    """
                    SELECT status FROM th_translations
                    WHERE content_id = ? AND lang_code = ? AND context_hash = ?
                    """,
                    (content_id, lang, context_hash),
                )
                existing_translation = cursor.fetchone()

                if existing_translation and existing_translation["status"] == TranslationStatus.TRANSLATED.value:
                    logger.debug(f"翻译 '{text_content[:20]}...' 到 '{lang}' 已存在并已翻译，跳过创建 PENDING 任务。")
                    continue

                params_to_insert.append(
                    (
                        content_id,
                        lang,
                        context_hash,
                        TranslationStatus.PENDING.value,
                        source_lang,
                        self.active_engine.VERSION,
                    )
                )

            if params_to_insert:
                cursor.executemany(insert_sql, params_to_insert)
                logger.info(
                    f"为 content_id={content_id} 确保了 {cursor.rowcount} 个新的 PENDING 任务。"
                )
            else:
                logger.info(f"为 content_id={content_id} 未创建新的 PENDING 任务 (可能已存在或已翻译)。")

    def run_garbage_collection(
        self, retention_days: int, dry_run: bool = False
    ) -> dict:
        """运行垃圾回收进程。"""
        logger.info(
            f"Coordinator 正在启动垃圾回收 (retention_days={retention_days}, dry_run={dry_run})..."
        )
        return self.handler.garbage_collect(
            retention_days=retention_days, dry_run=dry_run
        )

    def _validate_lang_codes(self, lang_codes: List[str]):
        """内部辅助方法：校验语言代码列表中的每个代码是否符合标准格式。"""
        lang_code_pattern = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")

        for code in lang_codes:
            if not lang_code_pattern.match(code):
                raise ValueError(
                    f"提供的语言代码 '{code}' 格式无效。 " "请使用标准格式，例如 'en', 'de', 'zh-CN'。"
                )

    def close(self):
        """关闭协调器及其持有的资源。"""
        logger.info("正在关闭 Coordinator...")
        self.handler.close()
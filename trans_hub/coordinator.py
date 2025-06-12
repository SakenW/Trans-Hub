"""
trans_hub/coordinator.py (v1.0 Final)

本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。
它采用动态引擎发现机制，并负责编排所有核心工作流。
"""
import time
import structlog
from typing import Dict, Generator, List, Optional

# [核心变更] 导入引擎注册表和总配置模型
from trans_hub.engine_registry import ENGINE_REGISTRY
from trans_hub.config import TransHubConfig

# 导入其他依赖
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
logger = structlog.get_logger(__name__)


class Coordinator:
    """
    同步版本的主协调器。
    实现了动态引擎加载、重试、速率限制等所有核心功能。
    """

    def __init__(
        self,
        config: TransHubConfig,
        persistence_handler: PersistenceHandler,
        # [可选] 允许外部注入自定义的速率限制器，增加灵活性
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """
        [v1.0 Final] 初始化协调器。

        Args:
            config: 一个包含所有配置的 TransHubConfig 对象。
            persistence_handler: 一个实现了 PersistenceHandler 接口的实例。
            rate_limiter: 一个可选的速率限制器实例。
        """
        self.config = config
        self.handler = persistence_handler
        self.active_engine_name = config.active_engine
        self.rate_limiter = rate_limiter

        logger.info("正在初始化 Coordinator...", available_engines=list(ENGINE_REGISTRY.keys()))

        # --- [核心变更] 动态创建活动引擎实例 ---
        # 1. 检查请求的引擎是否在已发现的注册表中
        if self.active_engine_name not in ENGINE_REGISTRY:
            raise ValueError(
                f"指定的活动引擎 '{self.active_engine_name}' 不可用。可能原因：1. 引擎不存在；2. 缺少相关依赖（如 'openai'）。"
                f"当前可用引擎: {list(ENGINE_REGISTRY.keys())}"
            )
        
        # 2. 从注册表中获取引擎的类
        EngineClass = ENGINE_REGISTRY[self.active_engine_name]
        
        # 3. 从总配置中获取该引擎的特定配置数据
        engine_config_data = getattr(config.engine_configs, self.active_engine_name, None)
        if not engine_config_data:
            raise ValueError(f"在配置中未找到活动引擎 '{self.active_engine_name}' 的配置。")
            
        # 4. 使用引擎自己的 CONFIG_MODEL 来创建其实例化的配置对象
        # Pydantic 会自动处理字典到模型的转换和校验
        engine_config_instance = EngineClass.CONFIG_MODEL(**engine_config_data.model_dump())
        
        # 5. 创建引擎实例并保存
        self.active_engine: BaseTranslationEngine = EngineClass(config=engine_config_instance)
        # --- 动态创建结束 ---
        
        logger.info(
            f"Coordinator 初始化完成。活动引擎: '{self.active_engine_name}', "
            f"速率限制器: {'已启用' if self.rate_limiter else '未启用'}"
        )

    # --- 后续所有方法 (`process_pending_translations`, `_convert...`, `request`, `run_gc`, `close`) ---
    # --- 的内部逻辑完全保持不变，因为它们依赖的 `self.active_engine` 和 `self.handler` ---
    # --- 已经由新的 `__init__` 方法正确地准备好了。 ---

    def process_pending_translations(
        self,
        target_lang: str,
        batch_size: int = 50,
        limit: Optional[int] = None,
        max_retries: int = 2,
        initial_backoff: float = 1.0,
    ) -> Generator[TranslationResult, None, None]:
        """处理指定语言的待翻译任务，内置重试和速率限制逻辑。"""
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
            
            engine_results: List[EngineBatchItemResult] = []
            for attempt in range(max_retries + 1):
                try:
                    if self.rate_limiter:
                        logger.debug("正在等待速率限制器...")
                        self.rate_limiter.acquire(1)
                        logger.debug("已获取速率限制器令牌，继续执行。")
                    
                    engine_results = self.active_engine.translate_batch(
                        texts=texts_to_translate,
                        target_lang=target_lang,
                    )
                    
                    has_retryable_errors = any(
                        isinstance(r, EngineError) and r.is_retryable for r in engine_results
                    )

                    if not has_retryable_errors:
                        logger.info(f"批次处理成功或遇到不可重试错误 (尝试次数: {attempt + 1})。")
                        break
                    
                    logger.warning(
                        f"批次中包含可重试的错误 (尝试次数: {attempt + 1}/{max_retries + 1})。"
                        "将在退避后重试..."
                    )

                except Exception as e:
                    logger.error(
                        f"引擎在处理批次时抛出异常 (尝试次数: {attempt + 1})", exc_info=True
                    )
                    engine_results = [EngineError(error_message=str(e), is_retryable=True)] * len(batch)

                if attempt < max_retries:
                    backoff_time = initial_backoff * (2 ** attempt)
                    logger.info(f"退避 {backoff_time:.2f} 秒...")
                    time.sleep(backoff_time)
                else:
                    logger.error(f"已达到最大重试次数 ({max_retries})，放弃重试。")

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

    def _convert_to_translation_result(
        self,
        item: ContentItem,
        engine_result: EngineBatchItemResult,
        target_lang: str,
    ) -> TranslationResult:
        """内部辅助方法，将引擎原始输出转换为统一的 TranslationResult DTO。"""
        if isinstance(engine_result, EngineSuccess):
            return TranslationResult(
                original_content=item.value,
                translated_content=engine_result.translated_text,
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                engine=self.active_engine_name,
                from_cache=False,
                context_hash=item.context_hash,
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
            )
        else:
            raise TypeError(f"未知的引擎结果类型: {type(engine_result)}")

    def request(
        self,
        target_langs: List[str],
        text_content: str,
        business_id: Optional[str] = None,
        context: Optional[dict] = None,
        source_lang: Optional[str] = None,
    ) -> None:
        """统一的翻译请求入口。"""
        logger.debug(
            f"收到翻译请求: business_id='{business_id}', "
            f"langs={target_langs}, content='{text_content[:30]}...'"
        )
        context_hash = get_context_hash(context)
        content_id = None
        if business_id:
            source_result = self.handler.update_or_create_source(
                text_content=text_content,
                business_id=business_id,
                context_hash=context_hash,
            )
            content_id = source_result.content_id
        
        with self.handler.transaction() as cursor:
            if not content_id:
                cursor.execute("SELECT id FROM th_content WHERE value = ?", (text_content,))
                row = cursor.fetchone()
                if row:
                    content_id = row['id']
                else:
                    cursor.execute("INSERT INTO th_content (value) VALUES (?)", (text_content,))
                    content_id = cursor.lastrowid

            insert_sql = """
                INSERT OR IGNORE INTO th_translations 
                (content_id, lang_code, context_hash, status, source_lang_code, engine_version)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            params_to_insert = [
                (
                    content_id, lang, context_hash, TranslationStatus.PENDING.value,
                    source_lang, self.active_engine.VERSION,
                ) for lang in target_langs
            ]
            cursor.executemany(insert_sql, params_to_insert)
            logger.info(f"为 content_id={content_id} 确保了 {cursor.rowcount} 个新的 PENDING 任务。")

    def run_garbage_collection(self, retention_days: int, dry_run: bool = False) -> dict:
        """运行垃圾回收进程。"""
        logger.info(
            f"Coordinator 正在启动垃圾回收 (retention_days={retention_days}, dry_run={dry_run})..."
        )
        return self.handler.garbage_collect(
            retention_days=retention_days, dry_run=dry_run
        )

    def close(self):
        """关闭协调器及其持有的资源。"""
        logger.info("正在关闭 Coordinator...")
        self.handler.close()
"""trans_hub/coordinator.py (v1.0 Final)

本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。
它采用动态引擎发现机制，并负责编排所有核心工作流，包括任务处理、重试、
速率限制、请求处理和垃圾回收等。
"""

import re
import time
from typing import (
    Any,
    Dict,
    Generator,
    List,
    Optional,
)

# 引入 Dict 和 Any，用于 context
import structlog

from trans_hub.config import TransHubConfig

# 核心变更: 导入引擎注册表和总配置模型
from trans_hub.engine_registry import ENGINE_REGISTRY
from trans_hub.engines.base import (
    BaseTranslationEngine,
)

# 确保 BaseTranslationEngine 已导入，其泛型现在应已正确配置
from trans_hub.interfaces import (
    PersistenceHandler,
)

# 确保 PersistenceHandler 协议已更新
# 导入其他依赖
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

# 获取一个模块级别的日志记录器
logger = structlog.get_logger(__name__)


class Coordinator:
    """同步版本的主协调器。
    实现了动态引擎加载、重试、速率限制等所有核心功能。
    """

    def __init__(
        self,
        config: TransHubConfig,
        persistence_handler: PersistenceHandler,
        # 可选: 允许外部注入自定义的速率限制器，增加灵活性
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """初始化协调器。

        Args:
        ----
            config: 一个包含所有配置的 TransHubConfig 对象。
            persistence_handler: 一个实现了 PersistenceHandler 接口的实例。
            rate_limiter: 一个可选的速率限制器实例。
        """
        self.config = config
        self.handler = persistence_handler
        self.active_engine_name = config.active_engine
        self.rate_limiter = rate_limiter

        logger.info(
            "正在初始化 Coordinator...", available_engines=list(ENGINE_REGISTRY.keys())
        )

        # --- 核心变更: 动态创建活动引擎实例 ---
        # 1. 检查请求的引擎是否在已发现的注册表中
        if self.active_engine_name not in ENGINE_REGISTRY:
            raise ValueError(
                f"指定的活动引擎 '{self.active_engine_name}' 不可用。"
                f"可能原因：1. 引擎不存在；2. 缺少相关依赖（如 'openai' 或 'translators'）。"
                f"当前可用引擎: {list(ENGINE_REGISTRY.keys())}"
            )

        # 2. 从注册表中获取引擎的类
        engine_class = ENGINE_REGISTRY[self.active_engine_name]

        # 3. 从总配置中获取该引擎的特定配置数据
        # 使用 getattr 安全获取，如果不存在则为 None
        engine_config_data = getattr(
            config.engine_configs, self.active_engine_name, None
        )
        if not engine_config_data:
            raise ValueError(
                f"在配置中未找到活动引擎 '{self.active_engine_name}' 的配置。"
            )

        # 4. 使用引擎自己的 CONFIG_MODEL 来创建其实例化的配置对象
        # Pydantic 会自动处理字典到模型的转换和校验
        engine_config_instance = engine_class.CONFIG_MODEL(
            **engine_config_data.model_dump()
        )

        # 5. 创建引擎实例并保存
        # Mypy 现在应能正确处理 BaseTranslationEngine 的泛型，
        # 并识别 engine_class(config=engine_config_instance) 的类型匹配。
        self.active_engine: BaseTranslationEngine[Any] = (
            engine_class(  # 使用 BaseTranslationEngine[Any] 确保 Mypy 兼容性
                config=engine_config_instance
            )
        )
        # --- 动态创建结束 ---

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
        # 在方法入口处进行语言代码校验
        self._validate_lang_codes([target_lang])

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
                        logger.debug("正在等待速率限制器令牌...")
                        self.rate_limiter.acquire(1)
                        logger.debug("已获取速率限制器令牌，继续执行翻译。")

                    # 调用活动引擎的批量翻译方法
                    engine_results = self.active_engine.translate_batch(
                        texts=texts_to_translate,
                        target_lang=target_lang,
                        # source_lang 和 context 可以在此按需传递
                    )

                    # 检查批次中是否包含可重试的错误
                    has_retryable_errors = any(
                        isinstance(r, EngineError) and r.is_retryable
                        for r in engine_results
                    )

                    if not has_retryable_errors:
                        logger.info(
                            f"批次处理成功或仅包含不可重试错误 (尝试次数: {attempt + 1})。"
                        )
                        break  # 如果没有可重试错误，则跳出重试循环

                    logger.warning(
                        f"批次中包含可重试的错误 (尝试次数: {attempt + 1}/{max_retries + 1})。"
                        "将在退避后重试批次..."
                    )

                except Exception as e:
                    # 捕获引擎抛出的任何异常，并将其转换为 EngineError
                    logger.error(
                        f"引擎在处理批次时抛出异常 (尝试次数: {attempt + 1})",
                        exc_info=True,
                    )
                    engine_results = [
                        EngineError(error_message=str(e), is_retryable=True)
                    ] * len(
                        batch
                    )  # 将整个批次标记为失败，并可重试

                if attempt < max_retries:
                    backoff_time = initial_backoff * (2**attempt)
                    logger.info(f"退避 {backoff_time:.2f} 秒后重试...")
                    time.sleep(backoff_time)
                else:
                    logger.error(
                        f"已达到最大重试次数 ({max_retries})，放弃当前批次的重试。"
                    )

            final_results_to_save: List[TranslationResult] = []
            for item, engine_result in zip(batch, engine_results):
                result = self._convert_to_translation_result(
                    item=item,
                    engine_result=engine_result,
                    target_lang=target_lang,
                )
                final_results_to_save.append(result)
                yield result  # 每次处理完一个内容项就立即 yield 结果

            # 批次处理完成后，统一保存翻译结果
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
                from_cache=False,  # 假定当前翻译不是来自缓存
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
                from_cache=False,  # 假定失败不是来自缓存
                context_hash=item.context_hash,
            )
        else:
            # 应该不会发生，除非 EngineBatchItemResult 的类型定义不完整
            raise TypeError(
                f"未知的引擎结果类型: {type(engine_result)}。预期 EngineSuccess 或 EngineError。"
            )

    def request(
        self,
        target_langs: List[str],
        text_content: str,
        business_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,  # 明确 context 为 Dict[str, Any]
        source_lang: Optional[str] = None,
    ) -> None:
        """统一的翻译请求入口。
        负责根据传入的文本和目标语言，创建或更新源记录，并生成待翻译任务。
        """
        # 在方法入口处进行语言代码校验
        self._validate_lang_codes(target_langs)
        if source_lang:
            self._validate_lang_codes([source_lang])

        logger.debug(
            f"收到翻译请求: business_id='{business_id}', "
            f"目标语言={target_langs}, 内容='{text_content[:30]}...'"
        )
        context_hash = get_context_hash(context)
        content_id: Optional[int] = None  # 明确 content_id 的类型

        # 如果提供了 business_id，则先更新或创建源记录
        if business_id:
            source_result = self.handler.update_or_create_source(
                text_content=text_content,
                business_id=business_id,
                context_hash=context_hash,
            )
            content_id = source_result.content_id

        # 核心逻辑：确保事务处理并记录翻译任务
        # Mypy 错误已在 interfaces.py 中修复
        with self.handler.transaction() as cursor:
            # 如果没有通过 business_id 找到 content_id，则尝试根据文本内容查找或插入
            if not content_id:
                cursor.execute(
                    "SELECT id FROM th_content WHERE value = ?", (text_content,)
                )
                row = cursor.fetchone()
                if row:
                    content_id = row["id"]  # 假设 row 是一个字典或支持按键访问
                else:
                    cursor.execute(
                        "INSERT INTO th_content (value) VALUES (?)", (text_content,)
                    )
                    content_id = cursor.lastrowid  # 获取新插入行的 ID

            if content_id is None:  # 理论上不应发生
                raise RuntimeError(
                    "Failed to determine content_id for translation task."
                )

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
                    TranslationStatus.PENDING.value,  # 将枚举值转换为字符串
                    source_lang,
                    self.active_engine.VERSION,
                )
                for lang in target_langs
            ]
            cursor.executemany(insert_sql, params_to_insert)
            logger.info(
                f"为 content_id={content_id} 确保了 {cursor.rowcount} 个新的 PENDING 任务。"
            )

    def run_garbage_collection(
        self, retention_days: int, dry_run: bool = False
    ) -> dict:
        """运行垃圾回收进程。
        此方法将调用持久化处理器的垃圾回收功能。
        Args:
            retention_days: 需要保留数据的天数，早于此时间的数据可能被清理。
            dry_run: 如果为 True，则只进行模拟运行，不实际删除数据。
        Returns:
            包含垃圾回收结果的字典。
        """
        logger.info(
            f"Coordinator 正在启动垃圾回收 (retention_days={retention_days}, dry_run={dry_run})..."
        )
        # Mypy 错误已在 interfaces.py 中修复
        return self.handler.garbage_collect(
            retention_days=retention_days, dry_run=dry_run
        )

    def _validate_lang_codes(self, lang_codes: List[str]):
        """内部辅助方法：校验语言代码列表中的每个代码是否符合标准格式。
        语言代码应遵循 ISO 639-1 (双字母) 或 ISO 639-2 + ISO 3166-1 alpha-2 (例如 'zh-CN')。
        """
        # 正则表达式：匹配 'en', 'zh-CN', 'pt-BR', 'gsw-CH' 等格式
        # [a-z]{2,3} 匹配 2 或 3 个小写字母，代表语言代码
        # (-[A-Z]{2})? 可选部分，匹配一个连字符和 2 个大写字母，代表国家/地区代码
        lang_code_pattern = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")

        for code in lang_codes:
            if not lang_code_pattern.match(code):
                raise ValueError(
                    f"提供的语言代码 '{code}' 格式无效。 "
                    "请使用标准格式，例如 'en', 'de', 'zh-CN'。"
                )

    def close(self):
        """关闭协调器及其持有的资源。
        主要负责关闭持久化处理器。
        """
        logger.info("正在关闭 Coordinator...")
        self.handler.close()

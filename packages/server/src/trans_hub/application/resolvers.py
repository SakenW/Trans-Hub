# packages/server/src/trans_hub/application/resolvers.py
"""
包含所有翻译解析策略的核心逻辑。
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from trans_hub_core.interfaces import PersistenceHandler

logger = structlog.get_logger(__name__)


class TranslationResolver:
    """
    负责执行翻译解析的核心业务逻辑，包含缓存检查、回退链等。
    """

    def __init__(self, handler: "PersistenceHandler"):
        """
        初始化解析器。

        Args:
            handler: 一个持久化处理器实例。
        """
        self._handler = handler

    async def resolve_with_fallback(
        self, project_id: str, content_id: str, target_lang: str, variant_key: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """
        从数据库解析翻译，并应用变体和语言回退链。

        这是系统“读模型”的核心算法。
        """
        # 1. 精确匹配 (语言 + 变体)
        result = await self._handler.get_published_translation(
            content_id, target_lang, variant_key
        )
        if result:
            logger.debug(
                "解析成功: 精确匹配",
                content_id=content_id,
                lang=target_lang,
                variant=variant_key,
            )
            return result[1], result[0]

        # 2. 如果请求了非默认变体，则回退到默认变体
        if variant_key != "-":
            result = await self._handler.get_published_translation(
                content_id, target_lang, "-"
            )
            if result:
                logger.debug(
                    "解析成功: 回退到默认变体", content_id=content_id, lang=target_lang
                )
                return result[1], result[0]

        # 3. 查询并应用语言回退链
        fallback_order = await self._handler.get_fallback_order(project_id, target_lang)
        if fallback_order:
            for fallback_lang in fallback_order:
                logger.debug(
                    "正在尝试语言回退",
                    content_id=content_id,
                    fallback_lang=fallback_lang,
                )
                # 回退时，总是使用默认变体
                result = await self._handler.get_published_translation(
                    content_id, fallback_lang, "-"
                )
                if result:
                    logger.debug(
                        "解析成功: 语言回退命中",
                        content_id=content_id,
                        hit_lang=fallback_lang,
                    )
                    return result[1], result[0]

        logger.debug(
            "解析失败: 所有回退均未命中", content_id=content_id, lang=target_lang
        )
        return None, None
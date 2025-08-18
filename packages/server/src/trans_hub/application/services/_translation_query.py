# packages/server/src/trans_hub/application/services/_translation_query.py
"""获取翻译的查询服务。"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any

import structlog
from trans_hub_uida import generate_uida

if TYPE_CHECKING:
    from trans_hub.config import TransHubConfig
    from trans_hub.infrastructure.uow import UowFactory
    from trans_hub_core.interfaces import CacheHandler
    from trans_hub.application.resolvers import TranslationResolver

logger = structlog.get_logger(__name__)


class TranslationQueryService:
    def __init__(
        self,
        uow_factory: UowFactory,
        config: TransHubConfig,
        cache: CacheHandler | None,
        resolver: TranslationResolver,
    ):
        self._uow_factory = uow_factory
        self._config = config
        self._cache = cache
        self._resolver = resolver

    async def execute(
        self,
        *,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        target_lang: str,
        variant_key: str = "-",
    ) -> dict[str, Any] | None:
        async with self._uow_factory() as uow:
            uida = generate_uida(keys)
            content_id = await uow.content.get_id_by_uida(
                project_id, namespace, uida.keys_sha256_bytes
            )
            if not content_id:
                logger.debug(
                    "内容未找到 (UIDA miss)", project_id=project_id, namespace=namespace
                )
                return None

        # 缓存键的生成现在依赖于 content_id
        cache_key = f"{self._config.redis.key_prefix}resolve:{content_id}:{target_lang}:{variant_key}"
        if self._cache:
            cached_result = await self._cache.get(cache_key)
            if cached_result:
                logger.debug("解析缓存命中", key=cache_key)
                return cached_result

        # 缓存未命中，调用 resolver 从数据库查询
        result_payload, _ = await self._resolver.resolve_with_fallback(
            project_id, content_id, target_lang, variant_key
        )

        # 回填缓存
        if result_payload and self._cache:
            ttl = self._config.redis.cache.ttl
            await self._cache.set(cache_key, result_payload, ttl=ttl)
            logger.debug("解析结果已写入缓存", key=cache_key)

        return result_payload

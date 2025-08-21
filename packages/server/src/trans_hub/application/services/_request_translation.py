# packages/server/src/trans_hub/application/services/_request_translation.py
"""处理翻译请求提交的应用服务。"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any
import uuid # [新增] 导入 uuid

from trans_hub.domain import tm as tm_domain
from trans_hub_core.types import TranslationStatus, Event
from trans_hub_uida import generate_uida
from ..events import TMApplied, TranslationSubmitted

if TYPE_CHECKING:
    from trans_hub.config import TransHubConfig
    from trans_hub.infrastructure.uow import UowFactory
    from trans_hub_core.uow import IUnitOfWork


class RequestTranslationService:
    def __init__(self, uow_factory: UowFactory, config: TransHubConfig):
        self._uow_factory = uow_factory
        self._config = config

    async def execute(
        self,
        *,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        source_payload: dict[str, Any],
        target_langs: list[str],
        source_lang: str | None = None,
        actor: str = "system",
        **kwargs: Any,
    ) -> str:
        final_source_lang = source_lang or self._config.default_source_lang
        if not final_source_lang:
            raise ValueError("源语言必须在请求或配置中提供。")

        uida = generate_uida(keys)

        async with self._uow_factory() as uow:
            await uow.misc.add_project_if_not_exists(project_id, project_id)

            content_id = await uow.content.get_id_by_uida(
                project_id, namespace, uida.keys_sha256_bytes
            )
            if content_id:
                await uow.content.update_payload(content_id, source_payload)
            else:
                content_id = await uow.content.add(
                    id=str(uuid.uuid4()), # [修复] 显式提供ID
                    project_id=project_id,
                    namespace=namespace,
                    keys_sha256_bytes=uida.keys_sha256_bytes,
                    source_lang=final_source_lang,
                    source_payload_json=source_payload,
                )

            source_text_for_tm = source_payload.get("text", "")
            source_fields = {
                "text": tm_domain.normalize_text_for_tm(source_text_for_tm)
            }
            reuse_sha = tm_domain.build_reuse_key(
                namespace=namespace, reduced_keys={}, source_fields=source_fields
            )

            for lang in target_langs:
                variant_key = kwargs.get("variant_key", "-")
                head_id, rev_no = await uow.translations.get_or_create_head(
                    project_id, content_id, lang, variant_key
                )
                await self._publish_event(
                    uow,
                    TranslationSubmitted(
                        head_id=head_id, project_id=project_id, actor=actor
                    ),
                )

                tm_hit = await uow.tm.find_entry(
                    project_id=project_id,
                    namespace=namespace,
                    reuse_sha=reuse_sha,
                    src_lang=final_source_lang,
                    tgt_lang=lang,
                    variant_key=variant_key,
                )

                if tm_hit:
                    tm_id, translated_payload = tm_hit
                    rev_id = await uow.translations.create_revision(
                        head_id=head_id,
                        project_id=project_id,
                        content_id=content_id,
                        target_lang=lang,
                        variant_key=variant_key,
                        status=TranslationStatus.REVIEWED,
                        revision_no=rev_no + 1,
                        translated_payload_json=translated_payload,
                        origin_lang="tm",
                    )
                    await uow.tm.link_revision_to_tm(rev_id, tm_id, project_id)
                    await self._publish_event(
                        uow,
                        TMApplied(
                            head_id=head_id,
                            project_id=project_id,
                            actor="system",
                            payload={"tm_id": tm_id},
                        ),
                    )
        return content_id

    async def _publish_event(self, uow: IUnitOfWork, event: Event) -> None:
        # [修复] 传递 project_id 和 event_id (使用新生成的 uuid)
        await uow.outbox.add(
            project_id=event.project_id,
            event_id=str(uuid.uuid4()),
            topic=self._config.worker.event_stream_name,
            payload=event.model_dump(mode="json"),
        )

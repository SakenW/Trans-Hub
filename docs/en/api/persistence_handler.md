async def connect(self) -> None:


async def close(self) -> None:


async def ensure_pending_translations(
    self,
    text_content: str,
    target_langs: list[str],
    source_lang: Optional[str],
    engine_version: str,
    business_id: Optional[str] = None,
    context_hash: Optional[str] = None,
    context_json: Optional[str] = None,
) -> None:


async def stream_translatable_items(
    self,
    lang_code: str,
    statuses: list[TranslationStatus],
    batch_size: int,
    limit: Optional[int] = None,
) -> AsyncGenerator[list[ContentItem], None]:


async def save_translations(self, results: list[TranslationResult]) -> None:


async def get_translation(
    self, text_content: str, target_lang: str, context: Optional[dict[str, Any]] = None,
) -> Optional[TranslationResult]:


async def get_business_id_for_content(
    self, content_id: int, context_hash: str
) -> Optional[str]:


async def touch_source(self, business_id: str) -> None:


async def garbage_collect(self, retention_days: int, dry_run: bool = False) -> dict[str, int]:


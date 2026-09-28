from __future__ import annotations
from typing import Optional

from core.providers.base import MediaProvider, ProviderFactory
from core.ratelimit.limiter import Limiter
from core.storage.repository import Storage
from core.types import GeneratedMedia, GenerationRequest, MediaKind, QuotaExceeded


class TextService:
    """Текстовая модальность. Сейчас: enhance-промпт. Дальше: диалог с памятью.

    Отдельный сервис, а не частичка image, потому что жизненный цикл
    и лимиты у текста свои.
    """

    def __init__(self, factory: ProviderFactory, limiter: Limiter, storage: Storage):
        self._factory = factory
        self._limiter = limiter
        self._storage = storage

    async def generate(self, request: GenerationRequest) -> GeneratedMedia:
        provider = self._factory.for_kind(MediaKind.TEXT)
        verdict = await self._limiter.check_and_consume(
            request.user_id, request.chat_id, unit="text"
        )
        if not verdict.allowed:
            raise QuotaExceeded(scope=verdict.scope, retry_after_seconds=verdict.retry_after_seconds)
        media = await provider.generate(request)
        return media

from __future__ import annotations

from core.providers.base import ProviderFactory
from core.ratelimit.limiter import Limiter
from core.storage.repository import Storage
from core.types import GenerationRequest, MediaKind


class VideoService:
    """Оркестрация видео: лимит → enhance → провайдер (create+poll)."""

    def __init__(self, factory: ProviderFactory, limiter: Limiter, storage: Storage,
                 enhancer=None):
        self._factory = factory
        self._limiter = limiter
        self._storage = storage
        self._enhancer = enhancer

    async def generate(self, request: GenerationRequest) -> tuple[object, int]:
        request.kind = MediaKind.VIDEO
        verdict = await self._limiter.check_and_commit(
            user_id=request.user_id, chat_id=request.chat_id or request.user_id,
            kind="video")
        provider = self._factory.for_kind(MediaKind.VIDEO)
        if self._enhancer is not None and not request.skip_enhance:
            import dataclasses
            request = dataclasses.replace(request, prompt=await self._enhancer(request))
        media = await provider.generate(request)
        await self._storage.save_generation(request.user_id, request.chat_id, media)
        return media, verdict.remaining

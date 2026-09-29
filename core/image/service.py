from __future__ import annotations

from core.providers.base import MediaProvider, ProviderFactory
from core.ratelimit.limiter import Limiter
from core.storage.repository import Storage
from core.types import GeneratedMedia, GenerationRequest, MediaKind, QuotaExceeded


class ImageService:
    """Единая точка входа для генерации картинок.

    Оркестрирует: лимиты → провайдер → история.
    tgbot вызывает только это; про HTTP он не знает.
    """

    def __init__(self, factory: ProviderFactory, limiter: Limiter, storage: Storage,
                 enhancer=None):
        self._factory = factory
        self._limiter = limiter
        self._storage = storage
        self._enhancer = enhancer   # async (GenerationRequest) -> str | None

    async def generate(self, request: GenerationRequest) -> tuple[GeneratedMedia, int]:
        provider = self._factory.for_kind(MediaKind.IMAGE)
        verdict = await self._limiter.check_and_consume(
            request.user_id, request.chat_id, unit="image"
        )
        if not verdict.allowed:
            raise QuotaExceeded(scope=verdict.scope, retry_after_seconds=verdict.retry_after_seconds)
        if self._enhancer is not None and not request.skip_enhance:
            request = _with_prompt(request, await self._enhancer(request))
        media = await provider.generate(request)
        await self._storage.save_generation(request.user_id, request.chat_id, media)
        return media, verdict.remaining

    async def edit(self, request: GenerationRequest) -> tuple[GeneratedMedia, int]:
        if not request.reference_images:
            raise ValueError("no reference images")
        provider = self._factory.for_kind(MediaKind.IMAGE)
        verdict = await self._limiter.check_and_consume(
            request.user_id, request.chat_id, unit="image"
        )
        if not verdict.allowed:
            raise QuotaExceeded(scope=verdict.scope, retry_after_seconds=verdict.retry_after_seconds)
        if self._enhancer is not None and not request.skip_enhance:
            request = _with_prompt(request, await self._enhancer(request))
        media = await provider.edit(request)
        await self._storage.save_generation(request.user_id, request.chat_id, media)
        return media, verdict.remaining


def _with_prompt(request: GenerationRequest, new_prompt: str) -> GenerationRequest:
    """Immutable-замена промпта: GeneratedMedia.prompt = финальный (улучшенный)."""
    import dataclasses
    return dataclasses.replace(request, prompt=new_prompt)

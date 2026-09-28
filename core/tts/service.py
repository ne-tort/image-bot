from __future__ import annotations

from core.providers.base import ProviderFactory
from core.types import GenerationRequest, MediaKind


class TTSService:
    """Задел: text → voice. Схема та же."""

    def __init__(self, factory: ProviderFactory):
        self._factory = factory

    async def generate(self, request: GenerationRequest):
        provider = self._factory.for_kind(MediaKind.AUDIO)
        request.kind = MediaKind.AUDIO
        return await provider.generate(request)

from __future__ import annotations
from typing import Protocol, runtime_checkable

from core.providers.errors import (
    Authentication, ContentRejected, CreditsExhausted, InvalidValue,
    NotConfigured, NotImplementedKind, ProviderError, RateLimited, Transient,
)
from core.types import GeneratedMedia, GenerationRequest, MediaKind

# единая точка импорта ошибок для потребителей
__all__ = [
    "MediaProvider", "ProviderFactory", "ProviderError", "RateLimited",
    "ContentRejected", "InvalidValue", "Transient", "Authentication",
    "CreditsExhausted", "NotConfigured", "NotImplementedKind",
]


@runtime_checkable
class MediaProvider(Protocol):
    """Единый контракт провайдера любой модальности.

    Семантика ошибок — core.providers.errors; тексты для юзера — слой tgbot.
    """

    name: str
    supported_kinds: frozenset[MediaKind]

    async def generate(
        self, request: GenerationRequest, *, timeout: float = 180.0
    ) -> GeneratedMedia: ...

    async def edit(
        self, request: GenerationRequest, *, timeout: float = 180.0
    ) -> GeneratedMedia: ...


@runtime_checkable
class ProviderFactory(Protocol):
    """DI-шов: сервисы получают провайдера для модальности, не зная деталей."""

    def for_kind(self, kind: MediaKind) -> MediaProvider: ...

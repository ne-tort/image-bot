from __future__ import annotations
from typing import Protocol, runtime_checkable

from core.types import MediaKind, GeneratedMedia, GenerationRequest


class ProviderError(Exception):
    """Носитель причин провайдера; wrapper переводит в i18n-тексты."""

    class RateLimited(ProviderError):
        """429. retry_after в секундах."""
        def __init__(self, retry_after: int = 60):
            super().__init__(f"provider rate limited, retry in {retry_after}s")
            self.retry_after = retry_after

    class ContentRejected(ProviderError):
        """Промпт отклонён модерацией/фильтром провайдера."""

    class Transient(ProviderError):
        """5xx / таймаут: можно повторить с backoff."""

    class Fatal(ProviderError):
        """401/403 и прочее, повтор бессмысленен."""


@runtime_checkable
class MediaProvider(Protocol):
    """Единый контракт для всех провайдеров и модальностей.

    Один класс может уметь несколько kinds (Pollinations умеет все).
    Меняется провайдер — меняется только адаптер в providers/.
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
    """DI-шов: tgbot получает провайдера, не зная о httpx."""

    def for_kind(self, kind: MediaKind) -> MediaProvider: ...

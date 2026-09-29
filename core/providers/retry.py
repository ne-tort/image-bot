from __future__ import annotations
import asyncio
import logging
import random
from dataclasses import dataclass

from core.providers.errors import Authentication, CreditsExhausted, NotConfigured

log = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_INTERVAL = 1.0
DEFAULT_BACKOFF_MULTIPLIER = 2.0
DEFAULT_MAX_INTERVAL = 30.0


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Экспоненциальный backoff с jitter.

    Jitter 0.8-1.2x — защита от thundering herd: много ботов не стучат
    в провайдера синхронно после его 429.
    """
    max_retries: int = DEFAULT_MAX_RETRIES
    initial_interval: float = DEFAULT_INITIAL_INTERVAL
    backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER
    max_interval: float = DEFAULT_MAX_INTERVAL

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt <= 0:
            return 0.0
        base = self.initial_interval * (self.backoff_multiplier ** (attempt - 1))
        capped = min(base, self.max_interval)
        return capped * (0.8 + random.random() * 0.4)


# Ошибки, при которых повтор бессмысленен в принципе.
_FATAL = (Authentication, CreditsExhausted, NotConfigured)


async def retry_call(fn, policy: RetryPolicy = RetryPolicy(), *, what: str = "call"):
    """Выполнить fn с ретраями. fn обязана кидать ProviderError-подклассы.

    Ожидание 429 включено в задержку: если провайдер сказал retry_after=30,
    мы не будем долбить его каждые 2 секунды.
    """
    last_error: Exception | None = None
    for attempt in range(policy.max_retries + 1):
        try:
            return await fn()
        except _FATAL:
            raise
        except ProviderErrorLike as exc:
            last_error = exc
            if not getattr(exc, "retryable", False):
                raise
            delay = policy.delay_for_attempt(attempt)
            if isinstance(exc, RateLimitedLike) and getattr(exc, "retry_after", 0) > delay:
                delay = min(exc.retry_after, policy.max_interval)
            if attempt >= policy.max_retries:
                raise
            log.info("retry %s attempt=%s delay=%.1fs: %r", what, attempt + 1, delay, exc)
            await asyncio.sleep(delay)
    raise last_error  # unreachable, для type-checker


# поздние алиасы чтобы не тащить циклический импорт в аннотации
from core.providers.errors import ProviderError as ProviderErrorLike  # noqa: E402
from core.providers.errors import RateLimited as RateLimitedLike  # noqa: E402

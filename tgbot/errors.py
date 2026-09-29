from __future__ import annotations

from core.i18n import I18n
from core.providers.base import (
    Authentication, ContentRejected, CreditsExhausted,
    InvalidValue, ProviderError, RateLimited, Transient,
)
from core.types import QuotaExceeded


async def friendly_error(i18n: I18n, locale: str, exc: Exception) -> str:
    """Единственный переводчик ошибок в тексты. Ни одного traceback юзеру.

    Семантика ошибок богаче HTTP: 429/подписки/кредиты/фильтры — у каждой
    свой тон (паттерн goose ProviderError).
    """
    if isinstance(exc, QuotaExceeded):
        if exc.scope.startswith("daily"):
            return i18n.t(locale, "err_own_limit_daily", hours=_hours_left(exc))
        return i18n.t(locale, "err_own_limit_hourly", minutes=max(1, exc.retry_after_seconds // 60))
    if isinstance(exc, RateLimited):
        return i18n.t(locale, "err_provider_429", minutes=max(1, int(exc.retry_after) // 60 or 1))
    if isinstance(exc, ContentRejected):
        return i18n.t(locale, "err_provider_reject")
    if isinstance(exc, InvalidValue):
        return i18n.t(locale, "err_provider_reject")
    if isinstance(exc, CreditsExhausted):
        return i18n.t(locale, "err_provider_auth")
    if isinstance(exc, Transient):
        return i18n.t(locale, "err_provider_down")
    if isinstance(exc, Authentication):
        return i18n.t(locale, "err_provider_auth")
    if isinstance(exc, ProviderError):
        return i18n.t(locale, "err_provider_down")
    return i18n.t(locale, "err_provider_down")


def _hours_left(exc: QuotaExceeded) -> int:
    return max(1, exc.retry_after_seconds // 3600)

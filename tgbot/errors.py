from __future__ import annotations

from core.i18n import I18n
from core.providers.base import ProviderError
from core.types import QuotaExceeded


async def friendly_error(i18n: I18n, locale: str, exc: Exception) -> str:
    """Единственный переводчик ошибок в тексты. Ни одного traceback юзеру.

    Паттерн из референса Gemini-image-bot: свои квоты и 429 — это UX, не 500.
    """
    if isinstance(exc, QuotaExceeded):
        if exc.scope.startswith("daily"):
            return i18n.t(locale, "err_own_limit_daily", hours=_hours_left(exc))
        return i18n.t(locale, "err_own_limit_hourly", minutes=max(1, exc.retry_after_seconds // 60))
    if isinstance(exc, ProviderError.RateLimited):
        return i18n.t(locale, "err_provider_429", minutes=max(1, exc.retry_after // 60))
    if isinstance(exc, ProviderError.ContentRejected):
        return i18n.t(locale, "err_provider_reject")
    if isinstance(exc, ProviderError.Transient):
        return i18n.t(locale, "err_provider_down")
    if isinstance(exc, ProviderError.Fatal):
        return i18n.t(locale, "err_provider_auth")
    return i18n.t(locale, "err_provider_down")


def _hours_left(exc: QuotaExceeded) -> int:
    return max(1, exc.retry_after_seconds // 3600)

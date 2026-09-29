from __future__ import annotations


class ProviderError(Exception):
    """Базовый класс ошибок провайдера. Носитель причины, не текста для юзера.

    Оболочка переводит в i18n-тексты (tgbot/errors.py), ядро — только семантика.
    """

    retryable: bool = False


class RateLimited(ProviderError):
    """429. Провайдер просит подождать. retry_after в секундах (потолок 1ч)."""
    retryable = True

    def __init__(self, retry_after: float = 60.0, details: str = ""):
        super().__init__(f"rate limited, retry in {retry_after}s {details}".strip())
        self.retry_after = min(float(retry_after), 3600.0)


class Transient(ProviderError):
    """5xx / таймаут / обрыв сети: можно повторить."""
    retryable = True


class ContentRejected(ProviderError):
    """Промпт отклонён фильтром: повтор бессмыслен, другая формулировка может пройти."""


class InvalidValue(ProviderError):
    """Кривой запрос (наша сторона): без повторов, дать юзеру подсказку."""


class Authentication(ProviderError):
    """401/403: ключ/сессия истекли. Владелец должен обновить креды."""


class CreditsExhausted(ProviderError):
    """Баланс/подписка кончились. top_up_url — куда отправить владельца."""
    def __init__(self, details: str = "", top_up_url: str = ""):
        super().__init__(f"credits exhausted: {details}".strip())
        self.top_up_url = top_up_url


class NotConfigured(ProviderError):
    """Провайдер не настроен (нет ключа/токена) — на этапе сборки, не запроса."""


class NotImplementedKind(ProviderError):
    """Провайдер объявил kind, но операция не поддерживается."""

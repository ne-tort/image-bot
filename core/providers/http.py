from __future__ import annotations
from email.utils import parsedate_to_datetime
import json
import time
from typing import Optional

import httpx

from core.providers.errors import (
    Authentication, ContentRejected, CreditsExhausted, InvalidValue, RateLimited, Transient,
)

MAX_RETRY_AFTER = 3600.0


def sanitize_url(url: str) -> str:
    """Убрать креды и query (там бывают ?key=...) для логов и ошибок."""
    try:
        u = httpx.URL(url)
    except Exception:
        return url
    u = u.copy_with(username=None, password=None, query=b"")
    return str(u)


def parse_retry_after(header_value: Optional[str], body: dict | None) -> float:
    """Retry-After по RFC 7231: секунды ИЛИ HTTP-date. Плюс тело
    error.metadata.retry_after_seconds (OpenRouter-форма), если точнее.

    Прошедшая дата = «повторять можно сейчас» (clock skew), не ошибка.
    Потолок 1 час: кривой retry-after=1e30 не заморозит бота.
    """
    if body:
        meta = (body.get("error") or {}).get("metadata") or {}
        secs = meta.get("retry_after_seconds")
        if isinstance(secs, (int, float)) and secs >= 0:
            return min(float(secs), MAX_RETRY_AFTER)
    if not header_value:
        return 60.0
    value = header_value.strip()
    try:
        return min(float(value), MAX_RETRY_AFTER)
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(value)
        delay = (target.timestamp() - time.time())
        return min(max(delay, 0.0), MAX_RETRY_AFTER)
    except Exception:
        return 60.0


def error_for_response(resp: httpx.Response) -> Exception:
    """HTTP-ответ → семантическая ошибка. Один маппинг для всех провайдеров.

    Парсит и {"error":{"message":...}}, и {"message":...} — как goose.
    """
    body = _safe_json(resp)
    message = _extract_message(body) or resp.text[:300]
    if resp.status_code == 429:
        return RateLimited(
            retry_after=parse_retry_after(resp.headers.get("retry-after"), body),
            details=message,
        )
    if resp.status_code in (401, 403):
        return Authentication(f"{resp.status_code}: {message}")
    if resp.status_code == 402:
        return CreditsExhausted(details=message)
    if resp.status_code in (400, 404, 422):
        # 404 от специфичного эндпоинта — не всегда «нет метода»: не гадаем,
        # считаем invalid value с текстом провайдера.
        return InvalidValue(f"{resp.status_code}: {message}")
    if resp.status_code >= 500:
        return Transient(f"upstream {resp.status_code}: {message}")
    # 2xx/3xx сюда не попадают; прочие 4xx — контент-фильтр или невалид
    return ContentRejected(f"{resp.status_code}: {message}")


def _safe_json(resp: httpx.Response) -> dict | None:
    try:
        data = json.loads(resp.text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _extract_message(body: dict | None) -> str:
    if not body:
        return ""
    err = body.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or "")
    if isinstance(err, str):
        return err
    return str(body.get("message") or "")

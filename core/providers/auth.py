from __future__ import annotations
import asyncio
import logging
import time
from typing import Optional, Protocol

from core.providers.errors import Authentication, NotConfigured

log = logging.getLogger(__name__)


class Credentials(Protocol):
    """Готовый к подстановке в запрос секрет + момент протухания."""

    async def get_headers(self) -> dict[str, str]: ...
    def expires_in(self) -> float: ...


class StaticApiKey:
    """env-ключ. Никогда не протухает сам: протухание покажет 401."""

    def __init__(self, api_key: str, scheme: str = "Bearer", header: str = "Authorization"):
        if not api_key:
            raise NotConfigured("api key is empty")
        self._value = f"{scheme} {api_key}" if scheme else api_key
        self._header = header

    async def get_headers(self) -> dict[str, str]:
        return {self._header: self._value}

    def expires_in(self) -> float:
        return float("inf")


class SessionToken:
    """Подписочная сессия (OAuth/web-login, паттерн Goose chatgpt_codex/gemini_oauth).

    token + expires_at; refresh через callable — провайдер подписки умеет
    обновить сессию. Кэш в памяти: refresh только когда близко к истечению
    или после 401 (реактивно), не по таймеру на каждый запрос.
    """

    def __init__(self, token: str, expires_at: float, refresh=None, leeway: float = 300.0):
        self._token = token
        self._expires_at = expires_at
        self._refresh = refresh          # async () -> tuple[str, float] | None
        self._leeway = leeway
        self._lock = asyncio.Lock()

    async def get_headers(self) -> dict[str, str]:
        if self._is_stale() and self._refresh is not None:
            async with self._lock:
                if self._is_stale():  # double-check после ожидания лока
                    await self._do_refresh()
        if not self._token:
            raise Authentication("session token expired and refresh failed")
        return {"Authorization": f"Bearer {self._token}"}

    def _is_stale(self) -> bool:
        return (self._expires_at - time.time()) < self._leeway

    async def _do_refresh(self) -> None:
        try:
            result = await self._refresh()
            if result is not None:
                self._token, self._expires_at = result
                log.info("session token refreshed, ttl=%.0fs", self.expires_in())
                return
        except Exception as exc:
            log.warning("session refresh failed: %r", exc)
        # refresh не удался: используем старый токен, 401 покажет правду
        if not self._token:
            raise Authentication("no usable session token") from None

    def expires_in(self) -> float:
        return max(0.0, self._expires_at - time.time())


class CommandCredentials:
    """Креды внешним процессом (паттерн goose AuthConfig).

    command исполняется напрямую (не через shell — без интерполяции),
    вывод = токен. refresh_interval секунд кэша; 0 = только реактивно,
    после ошибки аутентификации (конвенция Codex refresh_interval_ms: 0).
    """

    def __init__(self, command: list[str], refresh_interval: float = 3600.0,
                 timeout: float = 10.0, scheme: str = "Bearer"):
        self._command = command
        self._interval = refresh_interval
        self._timeout = timeout
        self._scheme = scheme
        self._token: str = ""
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_headers(self) -> dict[str, str]:
        stale = (time.time() - self._fetched_at) > self._interval
        if stale or not self._token:
            async with self._lock:
                if (time.time() - self._fetched_at) > self._interval or not self._token:
                    await self._fetch()
        return {"Authorization": f"{self._scheme} {self._token}"}

    def expires_in(self) -> float:
        return max(0.0, self._interval - (time.time() - self._fetched_at))

    async def _fetch(self) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            out, _err = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except Exception as exc:
            if not self._token:
                raise NotConfigured(f"credential command failed: {exc}") from exc
            return  # живём на старом токене
        if proc.returncode == 0:
            self._token = out.decode("utf-8", "ignore").strip().strip('"')
            self._fetched_at = time.time()
        elif not self._token:
            raise NotConfigured(f"credential command rc={proc.returncode}")


def static_from_env(value: Optional[str], *, name: str, scheme: str = "Bearer") -> StaticApiKey:
    """Валидирующий конструктор: пустое значение → NotConfigured с именем env."""
    if not value:
        raise NotConfigured(f"set {name}")
    return StaticApiKey(value, scheme=scheme)

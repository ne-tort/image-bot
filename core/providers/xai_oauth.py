from __future__ import annotations
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import httpx

log = logging.getLogger(__name__)

# Публичный клиент xAI (тот же, что используют grok-build и OpenClaw;
# публичные OAuth-клиенты не имеют секрета — PKCE/flow публичен по дизайну).
XAI_OAUTH_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_OAUTH_ISSUER = "https://auth.x.ai"
XAI_OAUTH_DISCOVERY = XAI_OAUTH_ISSUER + "/.well-known/openid-configuration"
XAI_OAUTH_SCOPE = "openid profile email offline_access grok-cli:access api:access"

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
DEFAULT_POLL_INTERVAL = 5.0
SLOW_DOWN_INCREMENT = 5.0
MIN_EXPIRY_FALLBACK = 600


@dataclass(slots=True)
class DeviceCode:
    """Фаза 1 RFC 8628: код для показа юзеру и девайс-код для поллинга."""
    verification_uri: str
    user_code: str
    device_code: str
    interval: float
    expires_in: int
    verification_uri_complete: str = ""


@dataclass(slots=True)
class Session:
    """Токены сессии. Формат совместим с ~/.grok/auth.json (goose/grok)."""
    access_token: str
    refresh_token: str = ""
    expires_at: float = 0.0
    email: str = ""
    user_id: str = ""

    @property
    def expires_in(self) -> float:
        return max(0.0, self.expires_at - time.time())

    def to_json(self) -> str:
        return json.dumps({
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "email": self.email,
            "user_id": self.user_id,
        })

    @classmethod
    def from_json(cls, raw: str) -> "Session":
        data = json.loads(raw)
        return cls(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            expires_at=float(data.get("expires_at", 0.0)),
            email=data.get("email", ""),
            user_id=data.get("user_id", ""),
        )


class XaiOAuthClient:
    """RFC 8628 device flow против auth.x.ai — официальные эндпоинты.

    Фазы разделены (как в grok-build): юзерский UI показывает URL и код
    между фазой 1 и поллингом фазы 2. Поллинг честный: authorization_pending
    ждёт, slow_down удлиняет интервал, denied/expired — терминальные.
    """

    def __init__(self, session_path: Path, http: Optional[httpx.AsyncClient] = None):
        self._session_path = session_path
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        self._endpoints: dict[str, str] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── discovery (кэш на процесс) ─────────────────────
    async def _discover(self) -> dict[str, str]:
        if not self._endpoints:
            resp = await self._http.get(XAI_OAUTH_DISCOVERY, headers={"Accept": "application/json"})
            resp.raise_for_status()
            doc = resp.json()
            self._endpoints = {
                "device": doc["device_authorization_endpoint"],
                "token": doc["token_endpoint"],
                "userinfo": doc.get("userinfo_endpoint", ""),
            }
            # защита: эндпоинты только от доверенного issuer
            for v in self._endpoints.values():
                if v and not v.startswith("https://auth.x.ai"):
                    raise RuntimeError(f"untrusted endpoint {v!r}")
        return self._endpoints

    # ── фаза 1: запрос device code ─────────────────────
    async def request_device_code(self) -> DeviceCode:
        eps = await self._discover()
        resp = await self._http.post(
            eps["device"],
            data={
                "client_id": XAI_OAUTH_CLIENT_ID,
                "scope": XAI_OAUTH_SCOPE,
                "referrer": "grok-build",
            },
            headers={"x-grok-client-surface": "ui"},
        )
        if resp.status_code == 404:
            raise RuntimeError("device flow not enabled for this deployment")
        resp.raise_for_status()
        doc = resp.json()
        code = DeviceCode(
            verification_uri=doc["verification_uri"],
            user_code=doc["user_code"],
            device_code=doc["device_code"],
            interval=float(doc.get("interval", DEFAULT_POLL_INTERVAL)),
            expires_in=int(doc.get("expires_in", MIN_EXPIRY_FALLBACK)),
            verification_uri_complete=doc.get("verification_uri_complete", ""),
        )
        _validate_user_code(code.user_code)
        return code

    # ── фаза 2: поллинг до подтверждения ───────────────
    async def poll_for_session(
        self, code: DeviceCode,
        on_status: Optional[Callable[[str], None]] = None,
        timeout: Optional[float] = None,
    ) -> Session:
        """Поллить token endpoint до подтверждения юзером.

        authorization_pending → ждём interval; slow_down → interval + 5 c
(конвенция RFC 8628); access_denied / expired — сразу ошибка.
        """
        eps = await self._discover()
        deadline = time.time() + (timeout if timeout else code.expires_in + 30)
        interval = code.interval or DEFAULT_POLL_INTERVAL
        while True:
            resp = await self._http.post(
                eps["token"],
                data={
                    "grant_type": DEVICE_GRANT,
                    "device_code": code.device_code,
                    "client_id": XAI_OAUTH_CLIENT_ID,
                },
            )
            if resp.status_code == 200:
                doc = resp.json()
                expires_at = time.time() + float(doc.get("expires_in", 3600))
                session = Session(
                    access_token=doc["access_token"],
                    refresh_token=doc.get("refresh_token", ""),
                    expires_at=expires_at,
                )
                if eps["userinfo"] and session.access_token:
                    await self._enrich(session, eps["userinfo"])
                self.save_session(session)
                return session
            err = ""
            try:
                err = resp.json().get("error", "")
            except Exception:
                pass
            if err == "authorization_pending":
                if time.time() >= deadline:
                    raise TimeoutError("device code expired before approval")
                await asyncio.sleep(interval)
                continue
            if err == "slow_down":
                interval += SLOW_DOWN_INCREMENT
                continue
            if err == "access_denied":
                raise PermissionError("user denied the login")
            if err == "expired_token":
                raise TimeoutError("device code expired")
            raise RuntimeError(f"token endpoint error: {err or resp.status_code}")

    async def _enrich(self, session: Session, userinfo_url: str) -> None:
        try:
            resp = await self._http.get(
                userinfo_url,
                headers={"Authorization": f"Bearer {session.access_token}"},
            )
            if resp.status_code == 200:
                doc = resp.json()
                session.email = str(doc.get("email", ""))
                session.user_id = str(doc.get("sub", ""))
        except Exception:
            pass  # обогащение опционально

    # ── персистентность: /data/auth/xai_session.json ──
    def load_session(self) -> Optional[Session]:
        try:
            raw = self._session_path.read_text(encoding="utf-8")
            session = Session.from_json(raw)
            if session.access_token:
                return session
        except FileNotFoundError:
            return None
        except Exception as exc:
            log.warning("corrupt session file: %r", exc)
        return None

    def save_session(self, session: Session) -> None:
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_path.write_text(session.to_json(), encoding="utf-8")
        try:
            self._session_path.chmod(0o600)  # owner-only, как grok auth.json
        except OSError:
            pass  # Windows

    def clear_session(self) -> None:
        try:
            self._session_path.unlink()
        except FileNotFoundError:
            pass


def _validate_user_code(user_code: str) -> None:
    if not all(c.isalnum() or c == "-" for c in user_code):
        raise RuntimeError("server returned invalid user_code format")
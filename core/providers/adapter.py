from __future__ import annotations
import base64
import logging
import os
import random
import time
from string import Template
from typing import Optional

import httpx

from core.providers.auth import (
    CommandCredentials, Credentials, SessionToken, StaticApiKey, static_from_env,
)
from core.providers.errors import NotImplementedKind, ProviderError
from core.providers.http import error_for_response
from core.providers.registry import spec_for
from core.providers.retry import RetryPolicy, retry_call
from core.providers.spec import EndpointSpec, ProviderSpec
from core.types import GeneratedMedia, GenerationRequest, MediaKind
from core.prompting.styles import apply_style
from core.providers.xai_oauth import Session as _XaiSession, XAI_OAUTH_CLIENT_ID

log = logging.getLogger(__name__)

_DEFAULTS = {
    "POLLINATIONS_BASE_URL": "https://gen.pollinations.ai",
    "POLLINATIONS_IMAGE_MODEL": "flux",
    "POLLINATIONS_EDIT_MODEL": "klein",
    "POLLINATIONS_TEXT_MODEL": "openai",
    "IMAGE_MODEL": "gpt-image-1",
    "IMAGE_EDIT_MODEL": "gpt-image-1",
    "TEXT_MODEL": "gpt-5-mini",
    "GROK_IMAGE_MODEL": "grok-imagine-image",
    "GROK_TEXT_MODEL": "grok-4.6",
    "GROK_BUILD_BASE_URL": "https://api.x.ai/v1",
}


def _interp(value: str) -> str:
    """${VAR} из env, с дефолтами. Неизвестная переменная → "".

    base_url и модели описаны шаблонами в спеке — инсталляция
    настраивается без правки кода (паттерн Goose env_vars).
    """
    mapping = {**_DEFAULTS, **os.environ}
    return Template(value).safe_substitute(mapping)


class SpecDrivenProvider:
    """Универсальный адаптер: одна реализация, много провайдеров.

    Разница между Pollinations / custom OpenAI-совместимым / подписками
    (Grok Build, Codex, Gemini OAuth) выражается ТОЛЬКО ProviderSpec + auth,
    не кодом. Это ядро вариативности:

      прямой API:      base_url из env, статический ключ
      подписка:        base_url фиксирован, токен сессии с refresh
      command-креды:   токен выдаёт внешний процесс

    Ошибки HTTP переводятся в семантику (http.error_for_response),
    ретраи с backoff+json — по policy, 429 ждёт столько, сколько сказал
    провайдер (в пределах потолка).
    """

    def __init__(self, spec: ProviderSpec, *, auth: Optional[Credentials] = None,
                 retry: Optional[RetryPolicy] = None, timeout: float = 180.0,
                 xai_session=None):
        self.spec = spec
        self._base_url = _interp(spec.base_url).rstrip("/")
        self._xai_session = xai_session
        self._auth = auth or self._resolve_session_auth()
        self._retry = retry or RetryPolicy()
        self.name = spec.name
        self.supported_kinds = spec.kinds
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=15.0),
            headers={"User-Agent": "image-bot/0.1"},
        )

    # ── фабрика: спека + env → готовый провайдер ─────────
    @classmethod
    def from_name(cls, name: str, *, retry: Optional[RetryPolicy] = None,
                  xai_session=None) -> "SpecDrivenProvider":
        """Собрать провайдера по имени спеки и окружению.

        auth_mode из спеки выбирает стратегию кредов:
          api_key  → StaticApiKey из api_key_env
          session  → SessionToken из env-токена + refresh-хук
          command  → CommandCredentials из env GREDENTIAL_COMMAND
        requires_auth=False и пустой ключ → аноним (провайдер допускает).
        """
        spec = spec_for(name)
        auth = cls._build_auth(spec)
        return cls(spec, auth=auth, retry=retry, xai_session=xai_session)

    def _resolve_session_auth(self) -> Optional[Credentials]:
        """Спеки session-типа берут токен из персистентной xAI-сессии.

        Сессия переживает рестарт (файл в volume). SessionToken с refresh-хуком:
        протухла — обновимся реактивно (grok-паттерн).
        """
        if self._xai_session is None or self.spec.auth_mode != "session":
            return None
        session = self._xai_session.load_session()
        if session is None:
            return None
        return SessionToken(
            session.access_token,
            expires_at=session.expires_at or (time.time() + 24 * 3600),
            refresh=_xai_refresh_hook(self._xai_session),
        )

    @staticmethod
    def _build_auth(spec: ProviderSpec) -> Optional[Credentials]:
        env_value = os.environ.get(spec.api_key_env, "") if spec.api_key_env else ""
        if spec.auth_mode == "session":
            if not env_value:
                # session-спека без env-токена: креды придут из xai_session
                # (device-flow /login) — соберёмся без auth, ошибки покажет запрос.
                # Прямой env-токен — ручной fallback для headless-инсталляций.
                return None
            return SessionToken(env_value, expires_at=_session_expiry_default())
        if spec.auth_mode == "command":
            command = _command_from_env(spec.name)
            if command is None:
                return _missing(spec)
            return CommandCredentials(command)
        # api_key
        if not env_value:
            return None if not spec.requires_auth else _missing(spec)
        return StaticApiKey(env_value)

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── контракт MediaProvider ───────────────────────────
    async def generate(self, request: GenerationRequest, *, timeout: float = 180.0) -> GeneratedMedia:
        if request.kind is MediaKind.IMAGE:
            return await self._image(request, timeout)
        if request.kind is MediaKind.TEXT:
            return await self._text(request, timeout)
        raise NotImplementedKind(f"{self.name}: generate({request.kind.value}) not implemented")

    async def edit(self, request: GenerationRequest, *, timeout: float = 180.0) -> GeneratedMedia:
        if request.kind is not MediaKind.IMAGE or not request.reference_images:
            raise NotImplementedKind("edit requires IMAGE kind and reference_images")
        return await self._image_edit(request, timeout)

    # ── модальности ──────────────────────────────────────
    async def _image(self, request: GenerationRequest, timeout: float) -> GeneratedMedia:
        prompt = apply_style(request.prompt, request.style)
        seed = request.seed if request.seed is not None else random.randrange(2 ** 31)
        w, h = (int(x) for x in request.resolution.value.split("x"))
        model = _interp(self.spec.image_model)
        if "{prompt}" in self.spec.endpoints.generate:
            # GET-форма Pollinations: /image/{prompt}
            async def call() -> httpx.Response:
                return await self._request(
                    "GET", self.spec.endpoints.generate.format(prompt=_url_escape(prompt)),
                    timeout=timeout,
                    params={"width": w, "height": h, "seed": seed, "model": model, "nologo": "true"},
                )
            resp = await retry_call(call, self._retry, what="image.generate")
            self._check(resp)
            return GeneratedMedia(kind=MediaKind.IMAGE, data=resp.content,
                                  prompt=prompt, model=model, seed=seed)
        # OpenAI-форма: POST /images/generations (база включает /v1)
        payload: dict = {"model": model, "prompt": prompt, "n": 1}
        if self.spec.edit_json_form:
            # xAI-подписка: aspect_ratio вместо size
            payload["aspect_ratio"] = _aspect_ratio(request.resolution)
        else:
            payload["size"] = request.resolution.value
        if self.spec.b64_response:
            payload["response_format"] = "b64_json"
        async def call() -> httpx.Response:
            return await self._request(
                "POST", self.spec.endpoints.generate,
                timeout=timeout,
                json=payload,
            )
        resp = await retry_call(call, self._retry, what="image.generate")
        self._check(resp)
        return await self._media_from_response(resp, model, prompt, seed)

    async def _image_edit(self, request: GenerationRequest, timeout: float) -> GeneratedMedia:
        prompt = apply_style(request.prompt, request.style)
        model = _interp(self.spec.image_edit_model)
        if self.spec.edit_json_form:
            # xAI-форма: JSON, image = data-URI; до 5 источников
            images = [_bytes_to_data_uri(img) for img in request.reference_images[:5]]
            payload: dict = {"model": model, "prompt": prompt,
                             "image": {"url": images[0], "type": "image_url"}}
            if len(images) > 1:
                payload["extra_images"] = [{"url": u, "type": "image_url"} for u in images[1:]]
            async def call_json() -> httpx.Response:
                return await self._request(
                    "POST", self.spec.endpoints.edit, timeout=timeout, json=payload,
                )
            resp = await retry_call(call_json, self._retry, what="image.edit")
            self._check(resp)
            return await self._media_from_response(resp, model, prompt, seed=None)
        # OpenAI-форма: multipart
        files = [("image[]", (f"ref{i}.jpg", img, "image/jpeg"))
                 for i, img in enumerate(request.reference_images)]
        async def call_form() -> httpx.Response:
            return await self._request(
                "POST", self.spec.endpoints.edit, timeout=timeout,
                data={"prompt": prompt, "response_format": "b64_json", "model": model},
                files=files,
            )
        resp = await retry_call(call_form, self._retry, what="image.edit")
        self._check(resp)
        return await self._media_from_response(resp, model, prompt, seed=None)

    async def _text(self, request: GenerationRequest, timeout: float) -> GeneratedMedia:
        model = _interp(self.spec.text_model)
        chat_base = _interp(self.spec.endpoints.chat_base_url) if self.spec.endpoints.chat_base_url else ""
        async def call() -> httpx.Response:
            return await self._request(
                "POST", self.spec.endpoints.chat, timeout=timeout,
                base_override=(chat_base or None),
                json={"model": model, "messages": [{"role": "user", "content": request.prompt}]},
            )
        resp = await retry_call(call, self._retry, what="text.generate")
        self._check(resp)
        payload = resp.json()
        text = payload["choices"][0]["message"]["content"]
        return GeneratedMedia(kind=MediaKind.TEXT, data=text, mime="text/plain",
                              prompt=request.prompt, model=model)

    # ── транспорт ────────────────────────────────────────
    async def _request(self, method: str, path: str, *, timeout: float,
                        base_override: "str | None" = None, **kw) -> httpx.Response:
        headers = dict(self.spec.headers)
        if self._auth is not None and base_override is None:
            headers.update(await self._auth.get_headers())
        base = base_override or self._base_url
        url = path if path.startswith("http") else base + path
        try:
            return await self._http.request(method, url, headers=headers,
                                            timeout=timeout, **kw)
        except httpx.TimeoutException as e:
            raise _transient(e) from e
        except httpx.TransportError as e:
            raise _transient(e) from e

    @staticmethod
    def _check(resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            raise error_for_response(resp)

    async def _media_from_response(self, resp: httpx.Response, model: str, prompt: str,
                                     seed: Optional[int]) -> GeneratedMedia:
        payload = resp.json()
        item = payload["data"][0]
        b64 = item.get("b64_json") or ""
        if b64:
            return GeneratedMedia(kind=MediaKind.IMAGE, data=base64.b64decode(b64),
                                  prompt=prompt, model=model, seed=seed)
        url = item.get("url") or ""
        if url:
            # url → байты: Telegram нужен файл, не ссылка
            data = await self._download(url)
            return GeneratedMedia(kind=MediaKind.IMAGE, data=data, prompt=prompt,
                                  model=model, seed=seed)
        raise InvalidValue("provider response has neither b64_json nor url")

    async def _download(self, url: str) -> bytes:
        """Скачать артефакт. URL прошёл проверку доверия провайдера (сессия xAI)."""
        try:
            resp = await self._http.get(url)
            self._check(resp)
            return resp.content
        except httpx.TimeoutException as e:
            raise _transient(e) from e
        except httpx.TransportError as e:
            raise _transient(e) from e


def _xai_refresh_hook(login_service):
    """Refresh-хук SessionToken: OAuth refresh grant, затем перечитывание файла.

    Двухступенчато:
    1. refresh_token grant к auth.x.ai/oauth2/token — обновляет протухший токен
    2. если grant не удался — hot-reload с диска (внешний /login обновил файл)

    Паттерн grok: сессия живёт в файле, обновление переживает рестарт.
    """
    async def _refresh():
        session = login_service.load_session()
        if not session:
            return None
        if session.refresh_token:
            refreshed = await _xai_refresh_grant(session, login_service)
            if refreshed is not None:
                return refreshed
        if session.access_token:
            return session.access_token, session.expires_at or (time.time() + 24 * 3600)
        return None
    return _refresh


async def _xai_refresh_grant(session, login_service):
    """POST refresh_token grant; успех — токен сохранён и возвращён."""
    import httpx as _httpx
    try:
        client = login_service.client
        eps = await client._discover()
        async with _httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(
                eps["token"],
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": session.refresh_token,
                    "client_id": XAI_OAUTH_CLIENT_ID,
                },
            )
        if resp.status_code != 200:
            log.warning("xai refresh grant failed: %s", resp.status_code)
            return None
        doc = resp.json()
        new_access = doc.get("access_token", "")
        if not new_access:
            return None
        import time as _time
        expires_at = _time.time() + float(doc.get("expires_in", 3600))
        new_session = _XaiSession(
            access_token=new_access,
            refresh_token=doc.get("refresh_token", session.refresh_token),
            expires_at=expires_at,
            email=session.email,
            user_id=session.user_id,
        )
        client.save_session(new_session)
        return new_access, expires_at
    except Exception as exc:
        log.warning("xai refresh grant error: %r", exc)
        return None


def _aspect_ratio(resolution) -> str:
    """Resolution (1344x768) → xAI aspect_ratio ('16:9' и т.п.).

    xAI принимает точные пропорции: 1:1, 3:4, 4:3, 9:16, 16:9, 2:3, 3:2, 21:9, auto…
    Выбираем ближайшую простую к пропорции разрешения.
    """
    w, h = (int(x) for x in resolution.value.split("x"))
    if w == h:
        return "1:1"
    ratio = w / h
    best, best_diff = "auto", float("inf")
    for cand in ("3:2", "2:3", "4:3", "3:4", "16:9", "9:16", "2:1", "1:2", "21:9", "5:2"):
        cw, ch = (float(x) for x in cand.split(":"))
        diff = abs(ratio - cw / ch)
        if diff < best_diff:
            best, best_diff = cand, diff
    return best


def _bytes_to_data_uri(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def _url_escape(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


def _transient(exc: Exception) -> ProviderError:
    from core.providers.errors import Transient
    return Transient(repr(exc))


def _missing(spec: ProviderSpec) -> Credentials:
    from core.providers.errors import NotConfigured
    hint = spec.api_key_env or f"{spec.name.upper()}_CREDENTIAL_COMMAND"
    raise NotConfigured(f"provider {spec.name}: set {hint}")


def _session_expiry_default() -> float:
    import time
    return time.time() + 24 * 3600  # web-сессии живут ~сутки; 401 обновит реактивно


def _command_from_env(name: str) -> Optional[list[str]]:
    raw = os.environ.get(f"{name.upper()}_CREDENTIAL_COMMAND", "")
    if not raw:
        return None
    import shlex
    return shlex.split(raw)
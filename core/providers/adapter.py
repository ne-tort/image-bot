from __future__ import annotations
import base64
import logging
import os
import random
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

log = logging.getLogger(__name__)

_DEFAULTS = {
    "POLLINATIONS_BASE_URL": "https://gen.pollinations.ai",
    "POLLINATIONS_IMAGE_MODEL": "flux",
    "POLLINATIONS_EDIT_MODEL": "klein",
    "POLLINATIONS_TEXT_MODEL": "openai",
    "IMAGE_MODEL": "gpt-image-1",
    "IMAGE_EDIT_MODEL": "gpt-image-1",
    "TEXT_MODEL": "gpt-5-mini",
    "GROK_IMAGE_MODEL": "grok-2-image",
    "GROK_TEXT_MODEL": "grok-4",
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
                 retry: Optional[RetryPolicy] = None, timeout: float = 180.0):
        self.spec = spec
        self._base_url = _interp(spec.base_url).rstrip("/")
        self._auth = auth
        self._retry = retry or RetryPolicy()
        self.name = spec.name
        self.supported_kinds = spec.kinds
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=15.0),
            headers={"User-Agent": "image-bot/0.1"},
        )

    # ── фабрика: спека + env → готовый провайдер ─────────
    @classmethod
    def from_name(cls, name: str, *, retry: Optional[RetryPolicy] = None) -> "SpecDrivenProvider":
        """Собрать провайдера по имени спеки и окружению.

        auth_mode из спеки выбирает стратегию кредов:
          api_key  → StaticApiKey из api_key_env
          session  → SessionToken из env-токена + refresh-хук
          command  → CommandCredentials из env GREDENTIAL_COMMAND
        requires_auth=False и пустой ключ → аноним (провайдер допускает).
        """
        spec = spec_for(name)
        auth = cls._build_auth(spec)
        return cls(spec, auth=auth, retry=retry)

    @staticmethod
    def _build_auth(spec: ProviderSpec) -> Optional[Credentials]:
        env_value = os.environ.get(spec.api_key_env, "") if spec.api_key_env else ""
        if spec.auth_mode == "session":
            if not env_value:
                return None if not spec.requires_auth else _missing(spec)
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
        # OpenAI-форма: POST /v1/images/generations
        async def call() -> httpx.Response:
            return await self._request(
                "POST", self.spec.endpoints.generate,
                timeout=timeout,
                json={"model": model, "prompt": prompt, "size": request.resolution.value,
                      "n": 1, "response_format": "b64_json"},
            )
        resp = await retry_call(call, self._retry, what="image.generate")
        self._check(resp)
        return self._media_from_b64(resp, model, prompt, seed)

    async def _image_edit(self, request: GenerationRequest, timeout: float) -> GeneratedMedia:
        prompt = apply_style(request.prompt, request.style)
        model = _interp(self.spec.image_edit_model)
        files = [("image[]", (f"ref{i}.jpg", img, "image/jpeg"))
                 for i, img in enumerate(request.reference_images)]
        async def call() -> httpx.Response:
            return await self._request(
                "POST", self.spec.endpoints.edit, timeout=timeout,
                data={"prompt": prompt, "response_format": "b64_json", "model": model},
                files=files,
            )
        resp = await retry_call(call, self._retry, what="image.edit")
        self._check(resp)
        return self._media_from_b64(resp, model, prompt, seed=None)

    async def _text(self, request: GenerationRequest, timeout: float) -> GeneratedMedia:
        model = _interp(self.spec.text_model)
        async def call() -> httpx.Response:
            return await self._request(
                "POST", self.spec.endpoints.chat, timeout=timeout,
                json={"model": model, "messages": [{"role": "user", "content": request.prompt}]},
            )
        resp = await retry_call(call, self._retry, what="text.generate")
        self._check(resp)
        payload = resp.json()
        text = payload["choices"][0]["message"]["content"]
        return GeneratedMedia(kind=MediaKind.TEXT, data=text, mime="text/plain",
                              prompt=request.prompt, model=model)

    # ── транспорт ────────────────────────────────────────
    async def _request(self, method: str, path: str, *, timeout: float, **kw) -> httpx.Response:
        headers = dict(self.spec.headers)
        if self._auth is not None:
            headers.update(await self._auth.get_headers())
        url = path if path.startswith("http") else self._base_url + path
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

    @staticmethod
    def _media_from_b64(resp: httpx.Response, model: str, prompt: str,
                         seed: Optional[int]) -> GeneratedMedia:
        payload = resp.json()
        item = payload["data"][0]
        if "b64_json" in item and item["b64_json"]:
            data = base64.b64decode(item["b64_json"])
        else:
            data = item["url"]  # str → GeneratedMedia.is_url
        return GeneratedMedia(kind=MediaKind.IMAGE, data=data, prompt=prompt,
                              model=model, seed=seed)


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
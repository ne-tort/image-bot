from __future__ import annotations
import base64
import random
from typing import Optional

import httpx

from core.types import GeneratedMedia, GenerationRequest, MediaKind
from core.providers.base import ProviderError
from core.prompting.styles import apply_style


class PollinationsProvider:
    """gen.pollinations.ai — единая точка для image/text/video/audio.

    Методы бросают ProviderError.* — оболочка решает, что показать юзеру.
    """

    name = "pollinations"
    supported_kinds = frozenset({MediaKind.IMAGE, MediaKind.TEXT, MediaKind.VIDEO, MediaKind.AUDIO})

    def __init__(self, api_key: Optional[str], base_url: str = "https://gen.pollinations.ai"):
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(180.0, connect=15.0),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── публичный контракт ────────────────────────────────
    async def generate(self, request: GenerationRequest, *, timeout: float = 180.0) -> GeneratedMedia:
        if request.kind is MediaKind.IMAGE:
            return await self._image(request, timeout)
        raise NotImplementedError(f"generate({request.kind}) пока в roadmap")

    async def edit(self, request: GenerationRequest, *, timeout: float = 180.0) -> GeneratedMedia:
        if request.kind is not MediaKind.IMAGE or not request.reference_images:
            raise ValueError("edit требует reference_images")
        return await self._image_edit(request, timeout)

    # ── внутренности ──────────────────────────────────────
    async def _image(self, request: GenerationRequest, timeout: float) -> GeneratedMedia:
        seed = request.seed if request.seed is not None else random.randrange(2**31)
        w, h = (int(x) for x in request.resolution.value.split("x"))
        prompt = apply_style(request.prompt, request.style)
        resp = await self._request(
            "POST", "/image/{prompt}", path_fmt={"prompt": prompt},
            timeout=timeout,
            params={"width": w, "height": h, "seed": seed, "nologo": "true"},
        )
        self._raise_for_status(resp)
        return GeneratedMedia(
            kind=MediaKind.IMAGE, data=resp.content, prompt=prompt,
            model="pollinations/flux", seed=seed,
        )

    async def _image_edit(self, request: GenerationRequest, timeout: float) -> GeneratedMedia:
        prompt = apply_style(request.prompt, request.style)
        files = [("image[]", (f"ref{i}.jpg", img, "image/jpeg"))
                 for i, img in enumerate(request.reference_images)]
        resp = await self._request(
            "POST", "/v1/images/edits",
            timeout=timeout,
            data={"prompt": prompt, "response_format": "b64_json", "model": "klein"},
            files=files,
        )
        self._raise_for_status(resp)
        payload = resp.json()
        b64 = payload["data"][0]["b64_json"]
        return GeneratedMedia(
            kind=MediaKind.IMAGE, data=base64.b64decode(b64), prompt=prompt,
            model="pollinations/klein",
        )

    async def _request(self, method: str, path: str, *, path_fmt: dict | None = None,
                       timeout: float, **kw) -> httpx.Response:
        url = path.format(**(path_fmt or {}))
        try:
            return await self._http.request(method, url, timeout=timeout, **kw)
        except httpx.TimeoutException as e:
            raise ProviderError.Transient(str(e)) from e
        except httpx.TransportError as e:
            raise ProviderError.Transient(str(e)) from e

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code == 429:
            ra = int(resp.headers.get("retry-after", "60"))
            raise ProviderError.RateLimited(retry_after=ra)
        if resp.status_code in (400, 422):
            raise ProviderError.ContentRejected(resp.text[:300])
        if resp.status_code in (401, 403):
            raise ProviderError.Fatal(f"auth failed: {resp.status_code}")
        if resp.status_code >= 500:
            raise ProviderError.Transient(f"upstream {resp.status_code}")

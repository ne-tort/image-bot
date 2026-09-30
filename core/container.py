from __future__ import annotations

from pathlib import Path

from core.config import CoreSettings
from core.image.service import ImageService
from core.xai_login import XaiLoginService
from core.mcp.tools import ToolContext, ToolRegistry
from core.providers.adapter import SpecDrivenProvider
from core.providers.base import ProviderFactory
from core.prompting.styles import enhance_with_text
from core.ratelimit import Limiter, LimitProfile
from core.storage import SqliteStorage
from core.text.service import TextService
from core.tts.service import TTSService
from core.types import GenerationRequest, MediaKind
from core.video.service import VideoService

_ANONYMOUS_OK = {"pollinations"}


class CoreContainer:
    """Композиция ядра. Единственная точка склейки.

    Провайдеры вариативны: имя из настроек → спека → адаптер.
    IMAGE_PROVIDER / TEXT_PROVIDER независимы: картинки могут ходить
    в Pollinations, а текст — в подписку Codex/Grok Build.
    """

    def __init__(self, settings: CoreSettings):
        self.settings = settings
        self.storage = SqliteStorage(settings.db_path)

        self._xai_login = XaiLoginService(Path(settings.xai_session_path))

        self._image_provider = SpecDrivenProvider.from_name(
            settings.image_provider, xai_session=self._xai_login
        )
        self._text_provider = SpecDrivenProvider.from_name(
            settings.text_provider, xai_session=self._xai_login
        )

        self._factory = _SplitProviderFactory(self._image_provider, self._text_provider)

        image_profile = LimitProfile(
            per_user_daily=settings.daily_image_limit,
            per_user_hourly=settings.hourly_image_limit,
            per_chat_daily=settings.group_daily_limit,
        )
        text_profile = LimitProfile(
            per_user_daily=settings.daily_text_limit,
            per_user_hourly=max(1, settings.daily_text_limit // 4),
            per_chat_daily=settings.daily_text_limit,
        )
        from core.prompting.enhancer import enhance_prompt
        self.image = ImageService(
            self._factory, Limiter(self.storage, image_profile), self.storage,
            enhancer=lambda req: enhance_prompt(self._text_provider, req),
        )
        self.text = TextService(self._factory, Limiter(self.storage, text_profile), self.storage)
        video_profile = LimitProfile(
            per_user_daily=settings.daily_video_limit,
            per_user_hourly=settings.hourly_video_limit,
            per_chat_daily=settings.daily_chat_limit,
        )
        self.video = VideoService(self._factory, Limiter(self.storage, video_profile), self.storage,
                                  enhancer=lambda req: enhance_prompt(self._text_provider, req))

    @property
    def text_provider(self):
        return self._text_provider
        self.tts = TTSService(self._factory)
        self.tools = ToolRegistry()
        self._register_tools()

    async def start(self) -> None:
        await self.storage.connect()

    async def stop(self) -> None:
        await self._image_provider.aclose()
        await self._text_provider.aclose()
        await self.storage.close()

    # ── MCP: текстовый ИИ командует генерацией ───────────
    @property
    def provider(self) -> SpecDrivenProvider:
        """Текстовый провайдер для enhance-флоу (кнопка ✨)."""
        return self._text_provider

    @property
    def xai_login(self) -> XaiLoginService:
        """Device-flow логин xAI: /login в чате бота."""
        return self._xai_login

    def _register_tools(self) -> None:
        async def generate_image(ctx: ToolContext, args: dict):
            req = GenerationRequest(
                prompt=args["prompt"], kind=MediaKind.IMAGE,
                user_id=ctx.user_id, chat_id=ctx.chat_id, style=args.get("style"),
            )
            return await self.image.generate(req)

        async def edit_image(ctx: ToolContext, args: dict):
            req = GenerationRequest(
                prompt=args["prompt"], kind=MediaKind.IMAGE,
                user_id=ctx.user_id, chat_id=ctx.chat_id,
                reference_images=[args["image"]],
            )
            return await self.image.edit(req)

        async def enhance_prompt(ctx: ToolContext, args: dict):
            return await enhance_with_text(args["prompt"], self._text_provider, ctx.locale)

        self.tools.register("generate_image", generate_image)
        self.tools.register("edit_image", edit_image)
        self.tools.register("enhance_prompt", enhance_prompt)


class _SplitProviderFactory:
    """Разные провайдеры на разные модальности. Сервисы этого не знают."""

    def __init__(self, image_provider, text_provider):
        self._image = image_provider
        self._text = text_provider

    def for_kind(self, kind: MediaKind):
        if kind is MediaKind.IMAGE:
            return self._image
        if kind is MediaKind.TEXT:
            return self._text
        # video/tts пока на тех же рельсах
        return self._text

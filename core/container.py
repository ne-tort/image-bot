from __future__ import annotations

from core.config import CoreSettings
from core.image.service import ImageService
from core.mcp.tools import ToolContext, ToolRegistry
from core.providers.base import ProviderFactory
from core.providers.pollinations import PollinationsProvider
from core.prompting.styles import enhance_with_text
from core.ratelimit import Limiter, LimitProfile
from core.storage import SqliteStorage
from core.text.service import TextService
from core.tts.service import TTSService
from core.types import GenerationRequest, MediaKind
from core.video.service import VideoService


class CoreContainer:
    """Композиция ядра. tgbot получает готовые сервисы, не зная деталей.

    Единственное место, где провайдер, лимиты и хранилище склеиваются.
    """

    def __init__(self, settings: CoreSettings):
        self.settings = settings
        self.storage = SqliteStorage(settings.db_path)
        self.provider = PollinationsProvider(
            settings.pollinations_api_key, settings.pollinations_base_url
        )
        self._factory = _SingleProviderFactory(self.provider)
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
        self.image = ImageService(self._factory, Limiter(self.storage, image_profile), self.storage)
        self.text = TextService(self._factory, Limiter(self.storage, text_profile), self.storage)
        self.video = VideoService(self._factory)
        self.tts = TTSService(self._factory)
        self.tools = ToolRegistry()
        self._register_tools()

    async def start(self) -> None:
        await self.storage.connect()

    async def stop(self) -> None:
        await self.provider.aclose()
        await self.storage.close()

    # ── MCP-инструменты: текстовый ИИ командует генерацией ─
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
            return await enhance_with_text(args["prompt"], self.provider, ctx.locale)

        self.tools.register("generate_image", generate_image)
        self.tools.register("edit_image", edit_image)
        self.tools.register("enhance_prompt", enhance_prompt)


class _SingleProviderFactory:
    """Сейчас провайдер один; смена/рост — без правок сервисов."""

    def __init__(self, provider):
        self._provider = provider

    def for_kind(self, kind: MediaKind):
        return self._provider

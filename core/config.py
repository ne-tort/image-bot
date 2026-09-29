from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    """Настройки ядра. Провайдеры вариативны: имя спеки → адаптер.

    IMAGE_PROVIDER / TEXT_PROVIDER независимо: картинки в Pollinations,
    текст в подписку (grok_build, codex_subscription, gemini_oauth) —
    или оба в custom OpenAI-совместимый.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""            # нужен только app/main; держим в одном месте

    image_provider: str = "pollinations"
    text_provider: str = "pollinations"

    # прямые API (OpenAI-совместимые, эндпоинты настраиваются)
    image_api_base_url: str = ""
    image_api_key: str = ""
    image_model: str = "gpt-image-1"
    image_edit_model: str = "gpt-image-1"
    text_api_base_url: str = ""
    text_api_key: str = ""
    text_model: str = "gpt-5-mini"

    # pollinations
    pollinations_api_key: str = ""
    pollinations_base_url: str = "https://gen.pollinations.ai"
    pollinations_image_model: str = "flux"
    pollinations_edit_model: str = "klein"
    pollinations_text_model: str = "openai"

    # подписки (не API)
    grok_build_base_url: str = ""
    grok_build_session_token: str = ""
    grok_image_model: str = "grok-2-image"
    grok_text_model: str = "grok-4"
    codex_base_url: str = ""
    gemini_base_url: str = ""
    gemini_session_token: str = ""

    daily_image_limit: int = 25
    hourly_image_limit: int = 5
    daily_text_limit: int = 100
    group_daily_limit: int = 50

    db_path: str = "/data/imagebot.db"
    default_locale: str = "ru"

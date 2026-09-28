from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""            # нужно только app; держим в одном месте, чтобы .env один
    provider: str = "pollinations"
    pollinations_api_key: str = ""
    pollinations_base_url: str = "https://gen.pollinations.ai"

    daily_image_limit: int = 25
    hourly_image_limit: int = 5
    daily_text_limit: int = 100
    group_daily_limit: int = 50

    db_path: str = "/data/imagebot.db"
    default_locale: str = "ru"

from __future__ import annotations
import asyncio
import logging
import os

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from core.config import CoreSettings
from core.container import CoreContainer
from core.i18n import I18n
from tgbot.router import attach_ctx_to_bot, build_dispatcher


async def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = CoreSettings()
    core = CoreContainer(settings)
    await core.start()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    i18n = I18n(default_locale=settings.default_locale)
    dp, ctx = build_dispatcher(core, i18n, owner_id=None)
    await attach_ctx_to_bot(bot, ctx)

    await bot.delete_webhook(drop_pending_updates=False)
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query", "my_chat_member"])
    finally:
        await core.stop()


if __name__ == "__main__":
    asyncio.run(main())

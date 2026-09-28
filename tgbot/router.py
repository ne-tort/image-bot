from __future__ import annotations
import logging

from aiogram import Bot, Dispatcher, Router

from core.container import CoreContainer
from core.i18n import I18n
from tgbot.context import BotContext
from tgbot.handlers.private import register_private
from tgbot.handlers.group import register_group

log = logging.getLogger(__name__)


def build_dispatcher(core: CoreContainer, i18n: I18n, owner_id: int | None) -> tuple[Dispatcher, BotContext]:
    router = Router(name="root")
    ctx = BotContext(core=core, i18n=i18n, owner_id=owner_id, router=router)

    register_private(router, ctx)
    register_group(router, ctx)

    dp = Dispatcher()
    dp["ctx"] = ctx
    dp.include_router(router)
    return dp, ctx


async def attach_ctx_to_bot(bot: Bot, ctx: BotContext) -> None:
    """Хендлеры берут ctx из bot.ctx — один источник, ноль глобалов."""
    bot.ctx = ctx  # type: ignore[attr-defined]

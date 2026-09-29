from __future__ import annotations
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from tgbot.context import BotContext
from tgbot.flows import run_generation_flow

log = logging.getLogger(__name__)


def register_private(router: Router, ctx: BotContext) -> None:
    router.message.register(_start, Command("start"))
    router.message.register(_help, Command("help"))
    router.message.register(_lang, Command("lang"))
    router.message.register(_style, Command("style"))
    router.message.register(_photo, F.photo)
    router.message.register(_text, F.text & ~F.text.startswith("/"))
    router.callback_query.register(_set_lang, F.data.startswith("lang:"))
    router.callback_query.register(_set_style, F.data.startswith("style:"))
    router.callback_query.register(_img_action, F.data.startswith("img:"))


async def _start(message: Message, state: FSMContext) -> None:
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    await ctx.core.storage.ensure_user(message.from_user.id)
    await message.answer(
        ctx.tr("ru", "start_private",
               limits=f"{ctx.core.settings.daily_image_limit} img/день")
    )


async def _help(message: Message) -> None:
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    locale = await ctx.core.storage.user_locale(message.from_user.id)
    await message.answer(ctx.tr(locale, "help_private"))


async def _lang(message: Message) -> None:
    from tgbot.ui import locale_kb
    await message.answer("Language / Язык", reply_markup=locale_kb())


async def _set_lang(cb: CallbackQuery) -> None:
    ctx: BotContext = cb.bot.ctx  # type: ignore[attr-defined]
    locale = cb.data.split(":", 1)[1]
    await ctx.core.storage.ensure_user(cb.from_user.id)
    await ctx.core.storage.set_user_locale(cb.from_user.id, locale)
    await cb.answer()
    await cb.message.edit_text(ctx.tr(locale, "lang_switched"))


async def _style(message: Message) -> None:
    from tgbot.ui import styles_kb
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    locale = await ctx.core.storage.user_locale(message.from_user.id)
    await message.answer(ctx.tr(locale, "settings_title"), reply_markup=styles_kb(locale))


async def _set_style(cb: CallbackQuery, state: FSMContext) -> None:
    ctx: BotContext = cb.bot.ctx  # type: ignore[attr-defined]
    style = cb.data.split(":", 1)[1]
    await state.update_data(style=style)
    await cb.answer()
    await cb.message.edit_text("✓" if style != "none" else "OK")


async def _photo(message: Message, state: FSMContext) -> None:
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    data = await state.get_data()
    photo_bytes = await message.bot.download(message.photo[-1])
    if not isinstance(photo_bytes, bytes):
        photo_bytes = photo_bytes.read()  # BytesIO fallback
    await run_generation_flow(
        ctx, message, message.caption or "",
        reference=[photo_bytes], style=data.get("style"),
    )


async def _text(message: Message, state: FSMContext) -> None:
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    data = await state.get_data()
    await run_generation_flow(ctx, message, message.text, style=data.get("style"))


async def _img_action(cb: CallbackQuery, state: FSMContext) -> None:
    """Re-try last / Original — per-user prompts from storage (not FSM)."""
    ctx: BotContext = cb.bot.ctx  # type: ignore[attr-defined]
    action = cb.data.split(":", 1)[1]
    await cb.answer()

    if action == "again":
        last = await ctx.core.storage.last_prompt(cb.from_user.id) or ""
        await run_generation_flow(ctx, cb.message, last)
        return

    if action == "original":
        original = await ctx.core.storage.original_prompt(cb.from_user.id)
        if not original:
            locale = await ctx.core.storage.user_locale(cb.from_user.id)
            await cb.message.reply(ctx.tr(locale, "original_prompt_none"))
            return
        # regenerate with the raw user prompt, bypassing the enhancer
        await run_generation_flow(ctx, cb.message, original, skip_enhance=True)


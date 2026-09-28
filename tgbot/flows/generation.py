from __future__ import annotations
import logging

from aiogram.types import Message, InlineKeyboardMarkup

from core.types import GenerationRequest, MediaKind, Resolution
from tgbot.context import BotContext
from tgbot.errors import friendly_error
from tgbot.ui import result_kb

log = logging.getLogger(__name__)

_MAX_PROMPT = 1000  # хранит смысл, отсекает пасты


async def run_generation_flow(
    ctx: BotContext, message: Message, prompt: str, *,
    reference: list[bytes] | None = None, style: str | None = None,
    resolution: Resolution = Resolution.SQ, chat_enabled_guard: bool = False,
) -> None:
    """Один поток для лички и групп: показать «рисую» → генерация → фото с кнопками.

    Различие личка/группа — только в оформлении (locale, reply-режим), не в логике.
    """
    prompt = prompt.strip()[:_MAX_PROMPT]
    locale = await _locale_of(ctx, message)

    if not prompt:
        if not reference:
            await message.answer(ctx.tr(locale, "err_empty_prompt"))
            return
        # фото без подписи → просим подпись (promptart-паттерн)
        await message.answer(ctx.tr(locale, "err_edit_no_photo"))
        return

    chat_id = message.chat.id if message.chat.id != message.from_user.id else None
    status = await message.answer(ctx.tr(locale, "working_edit" if reference else "working"))

    request = GenerationRequest(
        prompt=prompt, kind=MediaKind.IMAGE, user_id=message.from_user.id,
        chat_id=chat_id, resolution=resolution, style=style,
        reference_images=reference or (),
    )
    try:
        if reference:
            media, remaining = await ctx.core.image.edit(request)
        else:
            media, remaining = await ctx.core.image.generate(request)
    except Exception as exc:
        log.warning("generation failed user=%s: %r", message.from_user.id, exc)
        await status.edit_text(await friendly_error(ctx.i18n, locale, exc))
        return

    try:
        await status.delete()
    except Exception:
        pass
    sent = await message.answer_photo(
        media.data,
        caption=ctx.tr(locale, "done_prompt_footer", prompt=prompt),
        reply_markup=result_kb(locale),
    )
    await ctx.core.storage.set_last_media_file_id(message.from_user.id, sent.photo[-1].file_id)


async def _locale_of(ctx: BotContext, message: Message) -> str:
    await ctx.core.storage.ensure_user(message.from_user.id)
    return await ctx.core.storage.user_locale(message.from_user.id)

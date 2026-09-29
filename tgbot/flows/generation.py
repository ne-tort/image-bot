from __future__ import annotations
import logging

from aiogram.types import Message, MessageEntity

from core.types import GenerationRequest, MediaKind, Resolution
from tgbot.context import BotContext
from tgbot.errors import friendly_error
from tgbot.ui import result_kb

log = logging.getLogger(__name__)

_MAX_PROMPT = 1000


async def run_generation_flow(
    ctx: BotContext, message: Message, prompt: str, *,
    reference: list[bytes] | None = None, style: str | None = None,
    resolution: Resolution = Resolution.SQ, chat_enabled_guard: bool = False,
) -> None:
    """Один флоу для лички и групп: запрос → enhance → генерация → фото.

    Под фото — expandable-цитата (спойлер) с финальным промптом, кнопка
    «Оригинал» показывает запрос юзера как он был.
    """
    prompt = prompt.strip()[:_MAX_PROMPT]
    locale = await _locale_of(ctx, message)

    if not prompt:
        if not reference:
            await message.answer(ctx.tr(locale, "err_empty_prompt"))
            return
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

    # Финальный (улучшенный) промпт — в expandable-цитату: свёрнут по дефолту
    final_prompt = (media.prompt or prompt).strip()[:_MAX_PROMPT]
    header = ctx.tr(locale, "final_prompt_quote")
    caption = header + "\n" + final_prompt
    entities = [
        MessageEntity(type="expandable_blockquote",
                      offset=len(header) + 1, length=len(final_prompt)),
    ]
    if len(caption) > 1024:
        cut = 1024 - (len(header) + 1)
        final_prompt = final_prompt[:cut - 1]
        caption = header + "\n" + final_prompt
        entities = [MessageEntity(type="expandable_blockquote",
                                  offset=len(header) + 1, length=len(final_prompt))]

    sent = await message.answer_photo(
        _photo_input(media),
        caption=caption,
        caption_entities=entities,
        reply_markup=result_kb(locale),
    )
    await ctx.core.storage.set_last_media_file_id(message.from_user.id, sent.photo[-1].file_id)
    # оригинал юзера — для кнопки «Оригинал»
    await ctx.core.storage.save_original_prompt(message.from_user.id, prompt)


async def _locale_of(ctx: BotContext, message: Message) -> str:
    await ctx.core.storage.ensure_user(message.from_user.id)
    return await ctx.core.storage.user_locale(message.from_user.id)


def _photo_input(media):
    """media.data: bytes → BufferedInputFile; str (url/file_id) — как есть."""
    if isinstance(media.data, bytes):
        from aiogram.types import BufferedInputFile
        return BufferedInputFile(media.data, filename="image.jpg")
    return media.data

from __future__ import annotations
import logging

from aiogram.types import Message, MessageEntity

from core.types import GenerationRequest, MediaKind
from core.prompting.intent import route_intent, DEFAULT
from tgbot.context import BotContext
from tgbot.errors import friendly_error
from tgbot.ui import result_kb

log = logging.getLogger(__name__)

_MAX_PROMPT = 1000


async def run_generation_flow(
    ctx: BotContext, message: Message, prompt: str, *,
    reference: list[bytes] | None = None,
    is_video_attach: bool = False,
    style: str | None = None,
    skip_enhance: bool = False,
    chat_enabled_guard: bool = False,
) -> None:
    """Единый флоу: интент-роутинг → enhance → генерация → отправка.

    LLM решает image/video/quality/edit + aspect_ratio + нужен ли enhance.
    """
    prompt = prompt.strip()[:_MAX_PROMPT]
    locale = await _locale_of(ctx, message)
    has_image = bool(reference)

    if not prompt:
        if not reference and not is_video_attach:
            await message.answer(ctx.tr(locale, "err_empty_prompt"))
            return
        if not is_video_attach:
            await message.answer(ctx.tr(locale, "err_edit_no_photo"))
            return

    # ── 1. интент-роутинг (быстрый, короткий ответ LLM) ──
    intent = DEFAULT
    if not skip_enhance and prompt:
        intent = await route_intent(ctx.core.text_provider, prompt,
                                    has_image=has_image,
                                    has_video=is_video_attach)
        log.info("intent %s user=%s: %s", intent, message.from_user.id, intent.reason)

    # видео-вложение всегда в видео-модель
    if is_video_attach:
        intent = DEFAULT
        intent.action = "video"

    chat_id = message.chat.id if message.chat.id != message.from_user.id else None

    # ── 2. статус-сообщение ──
    status_key = "working"
    if intent.is_video:
        status_key = "working_video"
    elif reference:
        status_key = "working_edit"
    status = await message.answer(ctx.tr(locale, status_key))

    # ── 3. запрос ──
    request = GenerationRequest(
        prompt=prompt, kind=MediaKind.IMAGE, user_id=message.from_user.id,
        chat_id=chat_id, aspect_ratio=intent.aspect_ratio,
        duration=intent.duration if intent.is_video else None,
        style=style, reference_images=reference or (),
        skip_enhance=skip_enhance or not intent.enhance,
    )

    import asyncio as _aio
    long_key = "working_long_video" if intent.is_video else "working_long"
    async def _tick() -> None:
        await _aio.sleep(20)
        try:
            await status.edit_text(ctx.tr(locale, long_key))
        except Exception:
            pass
    ticker = _aio.create_task(_tick())
    try:
        if intent.is_video:
            request = _with_kind(request, MediaKind.VIDEO)
            media, remaining = await ctx.core.video.generate(request)
        elif reference:
            media, remaining = await ctx.core.image.edit(request)
        else:
            if intent.is_quality:
                request = _with_quality(request)
            media, remaining = await ctx.core.image.generate(request)
    except Exception as exc:
        ticker.cancel()
        log.warning("generation failed user=%s: %r", message.from_user.id, exc)
        await status.edit_text(await friendly_error(ctx.i18n, locale, exc))
        return
    finally:
        ticker.cancel()

    try:
        await status.delete()
    except Exception:
        pass

    # ── 4. отправка ──
    if media.kind is MediaKind.VIDEO:
        from aiogram.types import BufferedInputFile
        data = media.data if isinstance(media.data, bytes) else await _fetch(ctx, media.data)
        sent = await message.answer_video(
            BufferedInputFile(data, filename="video.mp4"),
            caption=(media.prompt or prompt)[:_MAX_PROMPT],
            reply_markup=result_kb(locale),
        )
        await ctx.core.storage.save_last_prompt(message.from_user.id, (media.prompt or prompt))
        await ctx.core.storage.save_original_prompt(message.from_user.id, prompt)
        return

    # картинка: цитата-спойлер с финальным промптом
    final_prompt = (media.prompt or prompt).strip()[:_MAX_PROMPT]
    if len(final_prompt) > 1024:
        final_prompt = final_prompt[:1023]
    caption = final_prompt
    entities = [
        MessageEntity(type="expandable_blockquote", offset=0, length=len(final_prompt)),
    ]
    sent = await message.answer_photo(
        _photo_input(media),
        caption=caption, caption_entities=entities,
        reply_markup=result_kb(locale),
    )

    # quality-режим: Telegram сжимает — прикладываем оригинал файлом
    if intent.is_quality:
        try:
            await message.answer(ctx.tr(locale, "attached_doc"))
            await message.answer_document(
                _photo_input(media),
                caption=(media.model or ""),
            )
        except Exception:
            pass

    await ctx.core.storage.set_last_media_file_id(message.from_user.id, sent.photo[-1].file_id)
    await ctx.core.storage.save_last_prompt(message.from_user.id, final_prompt)
    await ctx.core.storage.save_original_prompt(message.from_user.id, prompt)


def _with_kind(request, kind):
    import dataclasses
    return dataclasses.replace(request, kind=kind)


def _with_quality(request):
    import dataclasses
    return dataclasses.replace(request, quality=True)


async def _fetch(ctx, url: str) -> bytes:
    import httpx
    async with httpx.AsyncClient(timeout=120.0) as http:
        r = await http.get(url)
        r.raise_for_status()
        return r.content


async def _locale_of(ctx: BotContext, message: Message) -> str:
    await ctx.core.storage.ensure_user(message.from_user.id)
    return await ctx.core.storage.user_locale(message.from_user.id)


def _photo_input(media):
    if isinstance(media.data, bytes):
        from aiogram.types import BufferedInputFile
        return BufferedInputFile(media.data, filename="image.jpg")
    return media.data

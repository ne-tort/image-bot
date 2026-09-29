from __future__ import annotations
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ChatMemberAdministrator, ChatMemberOwner, ChatPermissions

from tgbot.context import BotContext
from tgbot.flows import run_generation_flow

log = logging.getLogger(__name__)

BOT_ID: int | None = None  # заполняется при старте


def register_group(router: Router, ctx: BotContext) -> None:
    router.message.register(_gen, Command("gen"))
    router.message.register(_photo_edit, F.photo, F.chat.type.in_({"group", "supergroup"}))
    router.message.register(_edit, Command("edit"))
    router.message.register(_enable, Command("enable"))
    router.message.register(_disable, Command("disable"))
    router.my_chat_member.register(_on_chat_member)
    router.message.register(_mention_or_reply, F.chat.type.in_({"group", "supergroup"}))


async def _gen(message: Message) -> None:
    """Группа: явная команда — предсказуемо, как советует capslock-референс."""
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    if not await ctx.core.storage.chat_enabled(message.chat.id):
        return
    prompt = message.text.split(maxsplit=1)[1] if len(message.text.split(maxsplit=1)) > 1 else ""
    await run_generation_flow(ctx, message, prompt, chat_enabled_guard=True)


async def _photo_edit(message: Message) -> None:
    """Фото с подписью в группе → edit, если чат активен и бот упомянут/это reply.

    В группах Privacy Mode выключен — бот видит всё; реагируем только на явные сигналы,
    чтобы не рисовать на каждый чих.
    """
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    if not await ctx.core.storage.chat_enabled(message.chat.id):
        return
    if not (message.caption and _is_directed_at_bot(message)):
        return
    photo = await message.bot.download(message.photo[-1], destination=bytearray())
    await run_generation_flow(ctx, message, message.caption, reference=[bytes(photo)])


async def _edit(message: Message) -> None:
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    if not await ctx.core.storage.chat_enabled(message.chat.id):
        return
    replied = message.reply_to_message
    if replied and replied.photo:
        photo = await message.bot.download(replied.photo[-1], destination=bytearray())
        prompt = message.text.split(maxsplit=1)
        await run_generation_flow(ctx, message, prompt[1] if len(prompt) > 1 else "", reference=[bytes(photo)])
    else:
        locale = await ctx.core.storage.user_locale(message.from_user.id)
        await message.answer(ctx.tr(locale, "err_edit_no_photo"))


async def _enable(message: Message) -> None:
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    if not _is_admin(message):
        return
    await ctx.core.storage.ensure_chat(message.chat.id, message.chat.title or "")
    await ctx.core.storage.set_chat_enabled(message.chat.id, True)
    locale = await ctx.core.storage.user_locale(message.from_user.id)
    await message.answer(ctx.tr(locale, "group_chat_enabled"))


async def _disable(message: Message) -> None:
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    if not _is_admin(message):
        return
    await ctx.core.storage.set_chat_enabled(message.chat.id, False)
    locale = await ctx.core.storage.user_locale(message.from_user.id)
    await message.answer(ctx.tr(locale, "group_chat_disabled"))


async def _on_chat_member(event) -> None:
    """Событие добавления/удаления бота — проактивное приветствие.

    Из референсов: лучший групповой бот не молчит, когда его добавили.
    """
    ctx: BotContext = event.bot.ctx  # type: ignore[attr-defined]
    new = event.new_chat_member
    if new.user.id != event.bot.id:
        return
    if new.status in ("kicked", "left"):
        await ctx.core.storage.set_chat_enabled(event.chat.id, False)
        return
    await ctx.core.storage.ensure_chat(event.chat.id, event.chat.title or "")
    await ctx.core.storage.set_chat_enabled(event.chat.id, True)
    try:
        await event.answer(ctx.tr("ru", "start_group"))
    except Exception:
        pass


async def _mention_or_reply(message: Message) -> None:
    """@упоминание или reply на бота → рисуем (patтерн Eugene-референса).

    Это fallback-хендлер: сработает, если ни один явный хендлер не поймал.
    """
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    if not await ctx.core.storage.chat_enabled(message.chat.id):
        return
    if not _is_directed_at_bot(message):
        return
    if not message.text:
        return
    bot_username = (await message.bot.me()).username
    text = message.text.replace(f"@{bot_username}", "").strip()
    await run_generation_flow(ctx, message, text)


def _is_directed_at_bot(message: Message) -> bool:
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == message.bot.id:
            return True
    entities = message.entities or (message.caption_entities or ())
    for e in entities:
        if e.type == "mention" and message.text and message.text[e.offset:e.offset + e.length].lower().lstrip("@") == message.bot.username.lower():
            return True
    return False


async def _is_admin(message: Message) -> bool:
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in ("administrator", "creator")

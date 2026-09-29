from __future__ import annotations
import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from tgbot.context import BotContext

log = logging.getLogger(__name__)


def register_login(router: Router, ctx: BotContext) -> None:
    router.message.register(_login, Command("login"))
    router.message.register(_logout, Command("logout"))


def _is_owner(ctx: BotContext, user_id: int) -> bool:
    # логин привязывает платную подписку — только владелец контейнера
    return ctx.owner_id is not None and user_id == ctx.owner_id


async def _login(message: Message) -> None:
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    user_id = message.from_user.id
    if not _is_owner(ctx, user_id):
        await message.answer(ctx.tr("ru", "login_only_owner"))
        return

    login = ctx.core.xai_login
    existing = login.load_session()
    if existing and existing.access_token:
        locale = await ctx.core.storage.user_locale(user_id)
        await message.answer(ctx.tr(locale, "login_already", email=existing.email or "unknown"))
        return

    client = login.client
    try:
        code = await client.request_device_code()
    except Exception as exc:
        log.warning("device code request failed: %r", exc)
        await message.answer(ctx.tr("ru", "login_failed", reason="xAI недоступен"))
        return

    locale = await ctx.core.storage.user_locale(user_id)
    await message.answer(
        ctx.tr(locale, "login_started", minutes=max(1, code.expires_in // 60))
        + "\n\n" + code.verification_uri
        + "\n\n"
        + ctx.tr(locale, "login_link_caption", code=code.user_code),
    )
    status = await message.answer(ctx.tr(locale, "login_waiting"))

    try:
        session = await client.poll_for_session(code)
    except PermissionError:
        await status.edit_text(ctx.tr(locale, "login_denied"))
        return
    except TimeoutError:
        await status.edit_text(ctx.tr(locale, "login_expired"))
        return
    except Exception as exc:
        log.warning("device login failed: %r", exc)
        await status.edit_text(ctx.tr(locale, "login_failed", reason=str(exc)[:120]))
        return

    await status.edit_text(
        ctx.tr(locale, "login_success", email=session.email or session.user_id or "?")
    )
    await _hot_swap_auth(ctx)


async def _logout(message: Message) -> None:
    ctx: BotContext = message.bot.ctx  # type: ignore[attr-defined]
    user_id = message.from_user.id
    if not _is_owner(ctx, user_id):
        await message.answer(ctx.tr("ru", "login_only_owner"))
        return
    locale = await ctx.core.storage.user_locale(user_id)
    if not ctx.core.xai_login.has_session():
        await message.answer(ctx.tr(locale, "logout_none"))
        return
    ctx.core.xai_login.clear()
    await message.answer(ctx.tr(locale, "logout_done"))
    await _hot_swap_auth(ctx)


async def _hot_swap_auth(ctx: BotContext) -> None:
    """После логина/логаута провайдеры grok_build берут сессию без рестарта.

    Паттерн hot-reload из grok: auth.json обновился — следующий запрос
    идёт с новым токеном. Мы перечитываем auth у активных провайдеров.
    """
    for provider in (ctx.core._image_provider, ctx.core._text_provider):
        if getattr(provider.spec, "auth_mode", "") == "session":
            provider._auth = provider._resolve_session_auth()

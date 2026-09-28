from __future__ import annotations

_LOCALES = ("ru", "en")

# Профессионально-разговорный тон: живой голос продукта, а не «Функция выполнена».
# Один файл — все строки, чтобы тон был единым. Никаких текстов в хендлерах.
_STRINGS: dict[str, dict[str, str]] = {
    # ── общие ─────────────────────────────────────────────
    "lang_name": {"ru": "Русский", "en": "English"},
    "lang_switched": {
        "ru": "Готово — теперь я говорю по-русски ✌",
        "en": "Done — speaking English now ✌",
    },

    # ── start / help ──────────────────────────────────────
    "start_private": {
        "ru": "Привет! Я рисую по слову, правлю по фото и не задаю лишних вопросов."
              + "\n\n"
              + "Просто пришли описание — или фото с подписью, что поменять."
              + "\n"
              + "Всё бесплатно, но с лимитами, чтобы всем хватило: {limits}.",
        "en": "Hey! I turn words into images, fix photos on request, and ask nothing extra."
              + "\n\n"
              + "Just send a description — or a photo captioned with what to change."
              + "\n"
              + "All free, with fair limits so there's enough for everyone: {limits}.",
    },
    "start_group": {
        "ru": "Всем привет 👋 Рисую по /gen, правлю по reply на фото. "
              "Просто напиши /gen описание — и погнали.",
        "en": "Hey everyone 👋 I draw with /gen and edit via reply to a photo. "
              "Just type /gen description — and off we go.",
    },
    "help_private": {
        "ru": "Текст → картинка: просто напиши описание"
              + "\n"
              + "Фото → правка: пришли фото и подписью что сделать"
              + "\n"
              + "/history — прошлое, /settings — настройки, /lang — язык",
        "en": "Text → image: just write a description"
              + "\n"
              + "Photo → edit: send a photo captioned with what to change"
              + "\n"
              + "/history — the past, /settings — settings, /lang — language",
    },

    # ── процесс ───────────────────────────────────────────
    "working": {"ru": "Рисую…", "en": "Drawing…"},
    "working_edit": {"ru": "Колдую над фото…", "en": "Working magic on the photo…"},
    "done_prompt_footer": {"ru": "«{prompt}»", "en": "“{prompt}”"},
    "again": {"ru": "Ещё раз", "en": "Again"},
    "enhance_prompt": {"ru": "✨ Сделать лучше", "en": "✨ Make it better"},
    "enhancing": {"ru": "Улучшаю промпт…", "en": "Polishing the prompt…"},

    # ── ошибки — человеческие, не traceback ───────────────
    "err_own_limit_daily": {
        "ru": "Лимит на сегодня исчерпан 🌙 Сброс в полночь UTC — {hours} ч. до свежих картинок.",
        "en": "Daily limit's spent 🌙 Reset at midnight UTC — {hours} h until fresh images.",
    },
    "err_own_limit_hourly": {
        "ru": "Полегче 🚀 Дай мне {minutes} мин — и продолжим.",
        "en": "Easy there 🚀 Give me {minutes} min and we'll continue.",
    },
    "err_provider_429": {
        "ru": "Сервис рисования сейчас занят. Попробуй через {minutes} мин — обычно помогает.",
        "en": "The drawing service is busy right now. Try in {minutes} min — usually helps.",
    },
    "err_provider_reject": {
        "ru": "Не могу это нарисовать — похоже, промпт наткнулся на фильтр. "
              "Попробуй сформулировать иначе.",
        "en": "I can't draw that — the prompt seems to have hit a filter. "
              "Try wording it differently.",
    },
    "err_provider_down": {
        "ru": "Рисовальный сервис прилёг. Нажми кнопку через минутку — попробую ещё раз.",
        "en": "The drawing service is taking a nap. Tap the button in a minute — I'll retry.",
    },
    "err_provider_auth": {
        "ru": "Кажется, у меня слетел ключ доступа. Если ты админ — глянь логи.",
        "en": "Looks like my access key got lost. If you're the admin — check the logs.",
    },
    "err_edit_no_photo": {
        "ru": "Пришли фото, и подписью напиши, что с ним сделать — я всё сделаю ✨",
        "en": "Send a photo and caption what to do with it — I'll handle the rest ✨",
    },
    "err_empty_prompt": {
        "ru": "Опиши хотя бы парой слов — что нарисовать?",
        "en": "Give me at least a couple of words — what should I draw?",
    },

    # ── группы ────────────────────────────────────────────
    "group_chat_enabled": {
        "ru": "Бот активен в этом чате. /gen описание — и рисуем.",
        "en": "Bot is active in this chat. /gen description — and we draw.",
    },
    "group_chat_disabled": {
        "ru": "Бот выключен в этом чате. Включить может админ командой /enable.",
        "en": "Bot is off in this chat. An admin can turn me on with /enable.",
    },
    "group_need_reply_or_mention": {
        "ru": "Я тут, если что: напиши /gen или ответь на фото.",
        "en": "I'm around if needed: type /gen or reply to a photo.",
    },
    "settings_title": {"ru": "Настройки", "en": "Settings"},
    "history_title": {"ru": "Последние", "en": "Recent"},
    "history_empty": {
        "ru": "Тут пока пусто. Исправим? Напиши, что нарисовать.",
        "en": "Nothing here yet. Let's fix that — tell me what to draw.",
    },
}


class I18n:
    """t(key, **kwargs) — весь i18n в одном вызове."""

    def __init__(self, default_locale: str = "ru"):
        self._default = default_locale if default_locale in _LOCALES else "ru"

    def t(self, locale: str, key: str, **kwargs) -> str:
        locale = locale if locale in _LOCALES else self._default
        entry = _STRINGS.get(key, {})
        s = entry.get(locale) or entry.get("ru", key)
        return s.format(**kwargs) if kwargs else s

    def locale_of(self, user_lang: str | None) -> str:
        if not user_lang:
            return self._default
        base = user_lang.split("-")[0].lower()
        return base if base in _LOCALES else self._default

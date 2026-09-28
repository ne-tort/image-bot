from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.prompting.styles import STYLES

# Inline-кнопки, не reply-клавиатуры: в группах reply-клавиатуры запрещены UX-бовом
# (promptart-референс это делает правильно — inline под фото).


def result_kb(locale: str) -> InlineKeyboardMarkup:
    """Кнопки под выданной картинкой. Единый для лички и группы."""
    again = "Ещё раз" if locale == "ru" else "Again"
    enhance = "✨ Сделать лучше" if locale == "ru" else "✨ Make it better"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=enhance, callback_data="img:enhance"),
         InlineKeyboardButton(text=again, callback_data="img:again")],
    ])


def styles_kb(locale: str) -> InlineKeyboardMarkup:
    rows, row = [], []
    for key, labels in STYLES.items():
        if key == "none":
            continue
        row.append(InlineKeyboardButton(text=labels.get(locale, labels["en"]), callback_data=f"style:{key}"))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(
        text="Как есть" if locale == "ru" else "As is", callback_data="style:none")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def locale_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
         InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")],
    ])

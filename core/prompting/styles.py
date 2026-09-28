from __future__ import annotations
from typing import Optional

from core.providers.base import MediaProvider, ProviderError

# Стили — модификаторы промпта, не magic-слова провайдера.
# Один источник правды и для tgbot-кнопок, и для core.
STYLES: dict[str, dict[str, str]] = {
    "none":     {"ru": "Как есть",   "en": "As is"},
    "photo":    {"ru": "📷 Фото",    "en": "📷 Photo"},
    "anime":    {"ru": "🌸 Аниме",   "en": "🌸 Anime"},
    "painting": {"ru": "🎨 Живопись", "en": "🎨 Painting"},
    "3d":       {"ru": "🧊 3D",      "en": "🧊 3D"},
    "cyberpunk": {"ru": "🌃 Киберпанк", "en": "🌃 Cyberpunk"},
    "sketch":   {"ru": "✏️ Набросок", "en": "✏️ Sketch"},
}

_SUFFIXES = {
    "photo": "photorealistic, 50mm lens, natural light, sharp focus",
    "anime": "anime style, vibrant colors, clean lineart",
    "painting": "oil painting, visible brush strokes, rich texture",
    "3d": "3d render, soft studio lighting, octane",
    "cyberpunk": "cyberpunk aesthetic, neon lights, cinematic mood",
    "sketch": "pencil sketch, hatching, monochrome",
}


def apply_style(prompt: str, style_key: Optional[str]) -> str:
    """KISS: стиль = суффикс промпта. Расширяемо до per-provider словарей."""
    if not style_key or style_key == "none":
        return prompt
    suffix = _SUFFIXES.get(style_key, "")
    return f"{prompt}, {suffix}" if suffix else prompt


# ── prompt enhancement через текстовый ИИ ────────────────
_SYSTEM_ENHANCE = {
    "ru": "Ты — художественный директор. Сделай промпт для генератора изображений сочным и конкретным: "
          "композиция, свет, атмосфера, стиль. Добавь 5-15 слов, сохрани смысл. Ответь только промптом.",
    "en": "You are an art director. Make the image-generation prompt juicy and specific: "
          "composition, light, mood, style. Add 5-15 words, keep the meaning. Reply with the prompt only.",
}


async def enhance_with_text(
    prompt: str, text_provider: MediaProvider, locale: str = "ru"
) -> str:
    """Текстовая модель улучшает промпт. Вызывается и кнопкой «✨», и ядром MCP.

    Провайдер обязан реализовать generate для TEXT — иначе Fatal.
    """
    from core.types import GenerationRequest, MediaKind
    try:
        media = await text_provider.generate(
            GenerationRequest(prompt=_SYSTEM_ENHANCE[locale if locale in _SYSTEM_ENHANCE else "ru"],
                              kind=MediaKind.TEXT, user_id=0)
        )
    except ProviderError as e:
        raise e
    # media.data может быть str (текст) — обрезаем до разумного
    raw = media.data if isinstance(media.data, str) else media.data.decode("utf-8", "ignore")
    enhanced = raw.strip().strip('"').strip("«»")
    return enhanced or prompt

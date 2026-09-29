from __future__ import annotations
from typing import Optional

# Стили — словарь тегов. Выбор стиля — функция UI-слоя (tgbot), не core.
STYLES: dict[str, dict[str, str]] = {
    "none":     {"ru": "Как есть",    "en": "As is"},
    "photo":    {"ru": "📷 Фото",      "en": "📷 Photo"},
    "anime":    {"ru": "🌸 Аниме",     "en": "🌸 Anime"},
    "painting": {"ru": "🎨 Живопись",  "en": "🎨 Painting"},
    "3d":       {"ru": "🧊 3D",        "en": "🧊 3D"},
    "cyberpunk": {"ru": "🌃 Киберпанк", "en": "🌃 Cyberpunk"},
    "sketch":   {"ru": "✏️ Скетч",     "en": "✏️ Sketch"},
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
    """KISS: стиль = детерминированный суффикс. Нет магии, нет per-provider веток."""
    if not style_key or style_key == "none":
        return prompt
    suffix = _SUFFIXES.get(style_key, "")
    return f"{prompt}, {suffix}" if suffix else prompt


# Промпт-улучшение через текстовую модель переехало в core/prompting/enhancer.py:
# SYSTEM_PROMPT (принципы Grok Imagine) + enhance_prompt().
async def enhance_with_text(prompt: str, text_provider: MediaProvider, locale: str = "ru") -> str:
    """Совместимость: улучшение через новый enhancer (для MCP-инструмента)."""
    from core.prompting.enhancer import SYSTEM_PROMPT, _extract_prompt
    from core.types import GenerationRequest, MediaKind
    try:
        media = await text_provider.generate(
            GenerationRequest(prompt=SYSTEM_PROMPT + "\n\nUser request:\n" + prompt,
                              kind=MediaKind.TEXT, user_id=0)
        )
        raw = media.data if isinstance(media.data, str) else str(media.data)
        out = _extract_prompt(raw)
        return out or prompt
    except Exception:
        return prompt  # деградация, не отказ

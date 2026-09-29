from __future__ import annotations
import logging

from core.providers.base import MediaProvider, ProviderError
from core.types import GenerationRequest, MediaKind

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You convert a user's image request into a final image prompt.

CRITICAL: The user's request is the SPEC, not a hint. Every subject, action,
style, and detail they named MUST appear in your output. You only ADD what is
missing (light, framing, palette, mood) to make it render well - you never
replace, drop, or 'improve' their choices.

COLORS - the precision rule:
- Name colors exactly as the source states them. A dark gray background is
  'dark gray', NEVER 'black'. If unsure, describe conservatively ('deep
  neutral gray') rather than guessing a stronger color word.
- NEVER introduce new colors, borders, frames, or vignettes that the user
  did not ask for. If the image has no border, do not mention borders at all.

Output format - one paragraph of natural English (or the user's language if
not English), 30-80 words, flowing sentences, no quotes, no markdown, no
explanations. Put the subject and its action in the first 15 words.
Order: subject -> style -> environment -> lighting -> mood. No negations.

Reply with the final prompt ONLY. No preamble."""

EDIT_SYSTEM_PROMPT = """You convert a user's IMAGE EDIT instruction into a final edit prompt.

CRITICAL: The user's instruction is the SPEC. Do exactly what they asked -
nothing extra. Never add borders, frames, vignettes, watermarks, or new
elements they did not request.

You will be given dominant colors of the image, measured from its actual
pixels (name + hex). Use them verbatim in the Keep clause when referring to
those regions - this is how the editor model finds the exact color.

FORMAT - exactly two sentences:
1. The imperative change: '[Do X].'
2. The keep clause: 'Keep [pose, faces, composition, lighting, colors with
   their hex codes from the measured list] unchanged.'
20-45 words total. Write in the user's language. No explanations, no preamble.

Reply with the final edit prompt ONLY."""


async def enhance_prompt(
    provider: MediaProvider, request: GenerationRequest,
) -> str:
    """Запрос юзера → финальный промпт через текстовую модель.

    Vision: при edit-запросе модель видит картинку + список доминирующих
    цветов (измеренных из пикселей — без ИИ-гаданий про цвета).
    Ошибка провайдера — деградация к оригиналу, не отказ.
    """
    from core.types import GenerationRequest as Req
    is_edit = bool(request.reference_images)
    try:
        media = await provider.generate(
            Req(
                prompt=_user_message(request),
                kind=MediaKind.TEXT,
                user_id=request.user_id,
                chat_id=request.chat_id,
                system_prompt=(EDIT_SYSTEM_PROMPT if is_edit else SYSTEM_PROMPT),
                vision_images=list(request.reference_images) if is_edit else (),
                extra={"no_retry": True},
            ),
            timeout=45.0,
        )
        text = _extract_prompt(str(media.data))
        if text:
            return text.strip()
    except ProviderError as exc:
        log.warning("prompt enhance failed (fallback to original): %r", exc)
    except Exception as exc:
        log.warning("prompt enhance crashed (fallback): %r", exc)
    return request.prompt


def _user_message(request: GenerationRequest) -> str:
    if request.reference_images:
        colors = _dominant_colors(request.reference_images[0])
        palette = (
            "Measured dominant colors of the image (use these in the Keep clause):\n"
            + "\n".join(f"- {name} ({hex_})" for name, hex_ in colors)
            if colors else "(no measured colors)"
        )
        return (
            "The user attached one image to edit. " + palette
            + "\nTheir instruction:\n"
            + request.prompt
        )
    return "The user wants a new image. Their request:\n" + request.prompt


def _extract_prompt(text: str) -> str:
    """Финальный промпт: последняя содержательная строка без префиксов."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    for line in reversed(lines):
        low = line.lower()
        if low.startswith("prompt:"):
            return line[7:].strip()
        if len(line) > 20 and not low.startswith(("the user", "i ", "okay", "note")):
            return line
    return lines[-1] if lines else ""


def _dominant_colors(image_bytes: bytes, top: int = 3) -> list[tuple[str, str]]:
    """Честные цвета из пикселей: кластеризация по квадрант-квантованию Pillow.

    Возвращает [(имя, '#HEX')]: имя — консервативное словесное описание
    (тёмно-серый ≠ чёрный). Ошибки — тихо пустой список (промпт не сломается).
    """
    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        small = img.resize((64, 64))
        quant = small.quantize(colors=6, method=Image.MEDIANCUT)
        palette = quant.getpalette()[:18]
        counts = sorted(quant.getcolors(64 * 64), reverse=True)[:top + 1]
        result = []
        for count, idx in counts[:top]:
            r, g, b = palette[idx * 3: idx * 3 + 3]
            hex_ = f"#{r:02X}{g:02X}{b:02X}"
            result.append((_color_name(r, g, b), hex_))
        return result
    except Exception:
        return []


def _color_name(r: int, g: int, b: int) -> str:
    """RGB → консервативное имя цвета. Тёмно-серый остаётся тёмно-серым."""
    mx, mn = max(r, g, b), min(r, g, b)
    sat = (mx - mn) / 255 if mx else 0
    light = (mx + mn) / 2 / 255
    if sat < 0.12:  # серая шкала — не сгущаем краски
        if light < 0.08:
            return "near-black"
        if light < 0.25:
            return "very dark gray"
        if light < 0.45:
            return "dark gray"
        if light < 0.62:
            return "medium gray"
        if light < 0.8:
            return "light gray"
        return "white"
    # хроматические — базовый оттенок
    import colorsys
    h = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[0] * 360
    base = ""
    for bound, name in ((15, "red"), (45, "orange"), (70, "yellow"), (160, "green"),
                        (200, "cyan"), (260, "blue"), (320, "purple"), (361, "magenta")):
        if h < bound:
            base = name
            break
    depth = "dark " if light < 0.35 else ("light " if light > 0.7 else "")
    return depth + base

from __future__ import annotations
import logging

from core.providers.base import MediaProvider, ProviderError
from core.types import GenerationRequest, MediaKind

log = logging.getLogger(__name__)

# Принципы: Grok Imagine field guides (front-load, natural language, порядок
# subject->style->environment->light->mood, imperative-правки, без negations).
# ГЛАВНОЕ правило: запрос юзера — закон. Мы уточняем, не подменяем.
SYSTEM_PROMPT = """You convert a user's image request into a final image prompt.

CRITICAL: The user's request is the SPEC, not a hint. Every subject, action,
style, and detail they named MUST appear in your output. You only ADD what is
missing (light, framing, palette, mood) to make it render well — you never
replace, drop, or 'improve' their choices.

If the request already contains visual specifics, keep them VERBATIM and extend
them. If it is short or vague, fill gaps conservatively — the most obvious,
mainstream interpretation, nothing exotic.

Output format — one paragraph of natural English (or the user's language if not
English), 30-80 words, comma-free flowing sentences, no quotes, no markdown,
no explanations. Put the subject and its action in the first 15 words.
Order: subject -> style -> environment -> lighting -> mood. No negations.

If you also receive an image, describe changes for it in imperative form:
"[Do X]. Keep [pose, faces, composition, lighting] unchanged." 15-40 words.
Use the image only to ground the edit — never contradict what the user asked.

Reply with the final prompt ONLY. No preamble."""


async def enhance_prompt(
    provider: MediaProvider, request: GenerationRequest,
) -> str:
    """Запрос юзера → финальный промпт через текстовую модель.

    Vision: если в запросе есть референсы И доступен vision — модель
    сначала видит картинку, потом пишет инструкцию правки.
    Ошибка провайдера — деградация к оригиналу, не отказ.
    """
    from core.types import GenerationRequest as Req
    try:
        media = await provider.generate(
            Req(
                prompt=_user_message(request),
                kind=MediaKind.TEXT,
                user_id=request.user_id,
                chat_id=request.chat_id,
                system_prompt=SYSTEM_PROMPT,
                vision_images=list(request.reference_images) if request.reference_images else (),
                extra={"no_retry": True},
            ),
            timeout=45.0,
        )
        text = _extract_prompt(str(media.data))
        if text:
            return text.strip()
    except ProviderError as exc:
        log.warning("prompt enhance failed (fallback to original): %r", exc)
    except Exception as exc:  # сеть и прочее — тоже деградируем тихо
        log.warning("prompt enhance crashed (fallback): %r", exc)
    return request.prompt


def _user_message(request: GenerationRequest) -> str:
    is_edit = bool(request.reference_images)
    if is_edit:
        return (
            "The user attached an image and wants to EDIT it. Their instruction:\n"
            + request.prompt
        )
    return "The user wants a new image. Their request:\n" + request.prompt


def _extract_prompt(text: str) -> str:
    """Финальный промпт: последняя содержательная строка без префиксов."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    # отбрасываем строки-рассуждения (модель иногда оставляет)
    for line in reversed(lines):
        low = line.lower()
        if low.startswith("prompt:"):
            return line[7:].strip()
        # строка-результат: без двоеточий-префиксов и слов-объяснений
        if len(line) > 20 and not low.startswith(("the user", "i ", "okay", "note")):
            return line
    return lines[-1] if lines else ""

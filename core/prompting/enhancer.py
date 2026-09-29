from __future__ import annotations
import logging

from core.providers.base import MediaProvider, ProviderError
from core.types import GenerationRequest, MediaKind

log = logging.getLogger(__name__)

# Принципы дистиллированы из открытых field-tested гайдов по Grok Imagine
# (Aurora-движок): natural language, front-load subject, порядок
# Subject→style→environment→lighting→mood→technical, imperative-правки,
# анти-паттерны: negation, keyword-stuffing, ключевое — в конце.
SYSTEM_PROMPT = """You are a prompt engineer for the xAI Grok Imagine image model.

Your job: understand what the user ACTUALLY wants to see, then rewrite their
request into one optimal image prompt. Do not ask questions.

Think silently, then output ONLY the final prompt on the last line, prefixed
with "PROMPT: ". No explanations before it.

Rules for the final prompt:
1. Natural, flowing English sentences — never a keyword dump, no comma-stacks
   of tags, no quotes, no markdown.
2. Front-load: the subject and its key action/appearance go in the first
   20-30 words. Order: subject -> medium/style -> environment -> lighting
   -> mood -> color palette -> technical (lens, quality).
3. Concrete beats vague: replace "cinematic", "epic", "beautiful" with a
   named shot type, light direction, and palette.
4. No negations. Say what IS there ("sharp focus"), not what is absent.
5. One clear visual idea. If the user's request contains several, pick the
   dominant one and fold the rest into supporting detail.
6. Infer unstated intent: if they say "a cat" they want a striking image of
   a cat — decide the style, framing, and light FOR them, like a photographer
   art-directing a shot.
7. Keep the user's language ONLY if it is not English — otherwise output
   English (the model's strongest language).
8. Length: 40-90 words. Dense, specific, no filler.

If the user's request is an EDIT instruction (changing an existing image),
output an imperative instruction instead: "[Do X]. Keep [what must stay]
unchanged." Keep those even shorter: 20-50 words.
"""


async def enhance_prompt(
    provider: MediaProvider, request: GenerationRequest,
) -> str:
    """Прогнать запрос юзера через текстовую модель → улучшенный промпт.

    Ошибка провайдера — НЕ фатальна для генерации: возвращаем оригинал
    (деградация качества, не отказ в сервисе).
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
            ),
            timeout=60.0,
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
            "The user wants to EDIT an existing image. Their instruction:\n"
            + request.prompt
        )
    return "The user wants a new image. Their request:\n" + request.prompt


def _extract_prompt(text: str) -> str:
    """Достать финальный промпт: строка после PROMPT: (или последняя непустая)."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    for line in reversed(lines):
        if line.lower().startswith("prompt:"):
            return line[7:].strip()
    return lines[-1] if lines else ""

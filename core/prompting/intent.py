from __future__ import annotations
import json
import logging

from core.providers.base import MediaProvider, ProviderError
from core.types import GenerationRequest, MediaKind

log = logging.getLogger(__name__)

ALLOWED_RATIOS = ("1:1", "2:3", "3:2", "9:16", "16:9")
ALLOWED_DURATIONS = (6, 10, 15)

INTENT_SYSTEM_PROMPT = """You are the intent router for an AI media generation bot.
Analyze the user's request and reply with ONE JSON object, nothing else:

{"action": "image | video | quality | edit",
 "aspect_ratio": "one of 1:1, 2:3, 3:2, 9:16, 16:9, or auto",
 "duration": 6 or 10 or 15 (videos only, or null),
 "enhance": true | false,
 "reason": "short explanation"}

Rules:
- "video": user asks for video, animation, clip, footage, motion, 'make it move',
  a video is attached, or they explicitly say video/анимация/видео/ролик.
  If an image is attached AND the phrasing is about animating it -> video.
- "edit": an image is attached and the request describes CHANGES to it
  (recolor, remove, replace, add, style transfer) without motion/animation.
- "quality": user EXPLICITLY asks for the best/highest quality, mentions
  quality mode, or asks for a print/HD/master version. Never choose quality
  implicitly.
- "image": everything else (default).
- aspect_ratio: pick by content when user did not specify:
  portrait/person/phone-screen -> 2:3 or 9:16; landscape/scene/wide -> 3:2 or 16:9;
  logo/icon/square/avatar -> 1:1. If the user explicitly asked for a ratio
  or shape (square/квадрат, wide/широкий, вертикальный, fullscreen/9:16), map it.
  Use "auto" only when truly ambiguous (then the bot uses 1:1 for images,
  16:9 for videos).
- enhance: false ONLY if the user's prompt already looks structured and
  complete (specific subject, action, style, composition - 30+ words of clear
  visual direction, or a fully specified professional prompt).
  True for anything short, vague, or casual.
- duration (video only): 6 (default), 10, or 15 seconds. Map the user's
  wording: 'short'/'mini' -> 6; standard clip or nothing said -> 6;
  'longer' -> 10; 'long'/'full version' -> 15. If the user gives exact
  seconds, pick the closest of 6/10/15.
- reason: max 8 words in the user's language.

Reply with the JSON object ONLY."""


class Intent:
    """Решение роутера: действие + пропорции + enhance."""

    def __init__(self, action: str, aspect_ratio: str, enhance: bool, reason: str = "",
                 duration: int = 6):
        self.action = action
        self.aspect_ratio = aspect_ratio if aspect_ratio in ALLOWED_RATIOS else ""
        self.enhance = bool(enhance)
        self.reason = reason
        self.duration = int(duration) if duration in ALLOWED_DURATIONS else 6

    @property
    def is_video(self) -> bool:
        return self.action == "video"

    @property
    def is_edit(self) -> bool:
        return self.action == "edit"

    @property
    def is_quality(self) -> bool:
        return self.action == "quality"

    def __repr__(self) -> str:
        return f"Intent({self.action}, {self.aspect_ratio!r}, enhance={self.enhance})"


DEFAULT = Intent("image", "", True)


async def route_intent(
    provider: MediaProvider,
    prompt: str,
    has_image: bool = False,
    has_video: bool = False,
) -> Intent:
    """LLM решает: что делать с запросом. Ошибки — деградация к дефолту."""
    user_msg = f"User request:\n{prompt}"
    if has_video:
        user_msg += "\n(A video is attached to the message.)"
    elif has_image:
        user_msg += "\n(An image is attached to the message.)"
    try:
        media = await provider.generate(
            GenerationRequest(
                prompt=user_msg, kind=MediaKind.TEXT, user_id=0,
                system_prompt=INTENT_SYSTEM_PROMPT,
                extra={"no_retry": True},
            ),
            timeout=30.0,
        )
        raw = str(media.data).strip()
        # достаём JSON-объект из ответа (модель может обернуть)
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return DEFAULT
        data = json.loads(raw[start:end + 1])
        return Intent(
            action=str(data.get("action", "image")).lower(),
            aspect_ratio=str(data.get("aspect_ratio", "")).lower(),
            enhance=data.get("enhance", True),
            reason=str(data.get("reason", ""))[:80],
            duration=data.get("duration") or 6,
        )
    except (ProviderError, Exception) as exc:
        log.warning("intent routing failed, fallback to default: %r", exc)
        return DEFAULT

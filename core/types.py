from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence


class MediaKind(str, Enum):
    IMAGE = "image"
    TEXT = "text"
    VIDEO = "video"
    AUDIO = "audio"


class Resolution(str, Enum):
    SQ = "1024x1024"
    LAND = "1344x768"
    PORT = "768x1344"
    LAND4 = "1152x896"
    PORT4 = "896x1152"


@dataclass(slots=True)
class GenerationRequest:
    """Универсальный запрос любого модальности-сервиса."""
    prompt: str
    kind: MediaKind
    user_id: int                      # для лимитов и истории, не для провайдера
    chat_id: Optional[int] = None
    aspect_ratio: str = "1:1"          # "1:1","2:3","3:2","9:16","16:9"; "" = на усмотрение ИИ
    n_images: int = 1                   # 1/2/4/8 вариантов для картинок
    quality: bool = False                # grok-imagine-image-quality по явной просьбе
    duration: Optional[int] = None       # сек для видео
    resolution: Resolution = Resolution.SQ
    style: Optional[str] = None       # ключ из core/prompting/styles.py
    seed: Optional[int] = None
    negative: Optional[str] = None
    reference_images: Sequence[bytes] = field(default_factory=tuple)  # для edit
    system_prompt: Optional[str] = None  # системный промпт для текстовых моделей
    skip_enhance: bool = False           # «Оригинал»: генерация без улучшения промпта
    vision_images: Sequence[bytes] = field(default_factory=tuple)  # для текстовой модели с vision
    extra: dict = field(default_factory=dict)


@dataclass(slots=True)
class GeneratedMedia:
    kind: MediaKind
    data: bytes | str                 # bytes = бинарник, str = url
    mime: str = "image/jpeg"
    prompt: str = ""
    model: str = ""
    seed: Optional[int] = None
    cost: float = 0.0                 # в «единицах», не деньгах

    @property
    def is_url(self) -> bool:
        return isinstance(self.data, str)


@dataclass(slots=True)
class QuotaExceeded(Exception):
    """Свои лимиты кончились. friendly-путь, а не 500."""
    scope: str                        # "daily_image" и т.п.
    retry_after_seconds: int = 0

    def __str__(self) -> str:
        return f"quota exceeded: {self.scope}"

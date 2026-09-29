from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from core.types import MediaKind


@dataclass(frozen=True, slots=True)
class EndpointSpec:
    """Настраиваемые эндпоинты. path от корня base_url.

    Пути — параметры: между инсталляциями одного провайдера пути различаются
    (gen.pollinations.ai vs self-hosted gateway). Дефолты — OpenAI-форма.
    """
    # base_url в спеках уже включает версию (/v1); пути относительны от неё
    generate: str = "/images/generations"
    edit: str = "/images/edits"
    chat: str = "/chat/completions"
    models: str = "/models"
    # отдельный хост для текста, если у провайдера так (pollinations)
    chat_base_url: str = ""


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """Декларативное описание провайдера — паттерн Goose fixed_provider_configs.

    Код адаптера один; меняется только спека. Три способа авторизации
    (паттерн Goose):
      - api_key  — статический ключ из env
      - session  — подписка: токен с refresh (web-login/OAuth)
      - command  — внешний процесс выдаёт креды (Codex-конвенция)
    """
    name: str
    display_name: str
    base_url: str                                    # поддерживает ${VAR}
    kinds: frozenset[MediaKind]
    auth_mode: str = "api_key"                       # api_key | session | command
    api_key_env: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    endpoints: EndpointSpec = field(default_factory=EndpointSpec)
    image_model: str = "flux"
    image_edit_model: str = "klein"
    text_model: str = "openai"
    requires_auth: bool = True
    b64_response: bool = True            # xAI-подписка отдаёт url, не b64
    edit_json_form: bool = False         # xAI edit: JSON {image:{url,type}}, не multipart
    description: str = ""

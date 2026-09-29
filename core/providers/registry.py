from __future__ import annotations

from core.providers.spec import EndpointSpec, ProviderSpec
from core.types import MediaKind

_ALL = frozenset(MediaKind)

# Спеки — данные, не код. Добавить провайдера = запись в словаре.
# ${VAR} в base_url и моделях интерполируется из env при сборке.
BUILTIN_SPECS: dict[str, ProviderSpec] = {
    "pollinations": ProviderSpec(
        name="pollinations",
        display_name="Pollinations",
        base_url="${POLLINATIONS_BASE_URL}",
        kinds=_ALL,
        auth_mode="api_key",
        api_key_env="POLLINATIONS_API_KEY",
        endpoints=EndpointSpec(
            generate="/image/{prompt}",
            edit="/images/edits",
            chat="/chat/completions",
            chat_base_url="https://text.pollinations.ai/openai",
        ),
        image_model="${POLLINATIONS_IMAGE_MODEL}",
        image_edit_model="${POLLINATIONS_EDIT_MODEL}",
        text_model="${POLLINATIONS_TEXT_MODEL}",
        requires_auth=False,
        description="Free community gen platform; key optional, recommended",
    ),
    "openai_compatible_image": ProviderSpec(
        name="openai_compatible_image",
        display_name="OpenAI-compatible images (custom)",
        base_url="${IMAGE_API_BASE_URL}",
        kinds=frozenset({MediaKind.IMAGE}),
        auth_mode="api_key",
        api_key_env="IMAGE_API_KEY",
        image_model="${IMAGE_MODEL}",
        image_edit_model="${IMAGE_EDIT_MODEL}",
        description="Any OpenAI-images-shaped API with configurable endpoints",
    ),
    "openai_compatible_text": ProviderSpec(
        name="openai_compatible_text",
        display_name="OpenAI-compatible text (custom)",
        base_url="${TEXT_API_BASE_URL}",
        kinds=frozenset({MediaKind.TEXT}),
        auth_mode="api_key",
        api_key_env="TEXT_API_KEY",
        text_model="${TEXT_MODEL}",
        description="Any OpenAI-chat-shaped API with configurable endpoints",
    ),
    "grok_build": ProviderSpec(
        name="grok_build",
        display_name="Grok Build (subscription)",
        base_url="${GROK_BUILD_BASE_URL}",
        kinds=_ALL,
        auth_mode="session",
        api_key_env="GROK_BUILD_SESSION_TOKEN",
        headers={"x-subscription": "grok-build"},
        b64_response=False,
        edit_json_form=True,
        image_model="${GROK_IMAGE_MODEL}",
        image_edit_model="${GROK_IMAGE_MODEL}",
        text_model="${GROK_TEXT_MODEL}",
        description="xAI Grok Build plan: web-session auth, not an API key",
    ),
    "codex_subscription": ProviderSpec(
        name="codex_subscription",
        display_name="ChatGPT/Codex (subscription)",
        base_url="${CODEX_BASE_URL}",
        kinds=frozenset({MediaKind.TEXT, MediaKind.IMAGE}),
        auth_mode="command",
        text_model="gpt-5.3-codex",
        image_model="gpt-image-1",
        description="ChatGPT Plus/Pro session via credential command",
    ),
    "gemini_oauth": ProviderSpec(
        name="gemini_oauth",
        display_name="Gemini (OAuth subscription)",
        base_url="${GEMINI_BASE_URL}",
        kinds=frozenset({MediaKind.TEXT, MediaKind.IMAGE}),
        auth_mode="session",
        api_key_env="GEMINI_SESSION_TOKEN",
        image_model="gemini-2.5-flash-image",
        text_model="gemini-2.5-flash",
        description="Google account OAuth session, cached locally",
    ),
}


def spec_for(name: str) -> ProviderSpec:
    try:
        return BUILTIN_SPECS[name]
    except KeyError:
        raise KeyError(
            f"unknown provider {name!r}; known: {", ".join(sorted(BUILTIN_SPECS))}"
        ) from None

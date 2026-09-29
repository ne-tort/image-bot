# Providers: variability

One adapter, many providers. What changes between installs is **data**, not code.

## How a provider is defined

A `ProviderSpec` (core/providers/registry.py) declares:

- `base_url` — supports `${VAR}` env interpolation
- `endpoints` — `generate`, `edit`, `chat`, `models` paths; configurable per install
- `kinds` — which modalities it serves
- `auth_mode` — one of three strategies (below)
- model names — also env-interpolated

## Three auth strategies (Goose pattern)

| Mode | How it works | Used by |
|---|---|---|
| `api_key` | static key from `api_key_env` | Pollinations, any OpenAI-compatible |
| `session` | subscription web-session token + reactive refresh (401 triggers it); cached in memory | Grok Build, Gemini OAuth |
| `command` | external command emits the credential; cached `refresh_interval` seconds; `0` = reactive-only (Codex convention) | ChatGPT/Codex subscription |

Session refresh is **lazy**: it only happens when the token is near expiry
(leeway 300s) or after an auth failure — never on a timer per request.

## Choosing providers

```ini
IMAGE_PROVIDER=pollinations      # free, no key needed
TEXT_PROVIDER=codex_subscription  # your ChatGPT Plus plan
```

Image and text providers are chosen **independently** — one service can draw
via a free API while text runs on your subscription.

## Built-in specs

- `pollinations` — free community platform, key optional
- `openai_compatible_image` / `openai_compatible_text` — any API with
  OpenAI-shaped endpoints, fully configurable base URL + models
- `grok_build` — xAI Grok Build plan (subscription, not an API key)
- `codex_subscription` — ChatGPT Plus/Pro session via credential command
- `gemini_oauth` — Google account OAuth session

## Error semantics & retry

Every HTTP failure becomes a typed error (`RateLimited`, `ContentRejected`,
`InvalidValue`, `Authentication`, `CreditsExhausted`, `Transient`) — never a raw
status code. Retries: exponential backoff (base 1s, ×2, cap 30s) with 0.8-1.2×
jitter against thundering-herd; a 429's `Retry-After` (seconds or HTTP-date,
capped at 1h) overrides the computed delay. Fatal errors (auth, credits) never
retry.

## Adding a provider

One dict entry in `BUILTIN_SPECS`. If its wire format matches an existing
shape (OpenAI images / OpenAI chat / Pollinations GET), zero new code.

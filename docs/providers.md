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

## xAI Grok Build: subscription login in Docker

Grok Build is a SuperGrok/X Premium+ **subscription**, not an API key. Login
uses the official **OAuth device-code flow** (RFC 8628) against `auth.x.ai`
— the same flow as `grok login --device-auth`, designed exactly for
headless/Docker environments:

1. Set `IMAGE_PROVIDER=grok_build` (and/or `TEXT_PROVIDER`), set
   `BOT_OWNER_ID` to your Telegram user id.
2. `docker compose up -d`, then send `/login` **in the bot's private chat**.
3. The bot replies with a verification URL and a code. Open the URL on any
   device (phone!), enter the code, approve.
4. Done. The session (access + refresh token, email) is stored at
   `/data/auth/xai_session.json` — a Docker volume, so it **survives
   container restarts and image upgrades**.

Details:

- Discovery is live from `https://auth.x.ai/.well-known/openid-configuration`
  (verified endpoints, trusted-issuer check — a hijacked discovery doc is
  rejected).
- The session file is written with owner-only permissions (0600, like grok's
  `auth.json`).
- Polling is RFC 8628-honest: `authorization_pending` waits the requested
  interval, `slow_down` extends it, `access_denied`/`expired_token` fail
  immediately with human copy.
- **Hot-reload**: after login/logout the providers pick up the new token on
  the next request — no container restart (the grok `auth.json` pattern).
- `/login` is restricted to `BOT_OWNER_ID` (it's *your* paid subscription).
  `/logout` clears the session file.
- A raw token in `GROK_BUILD_SESSION_TOKEN` still works as a headless
  fallback.

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

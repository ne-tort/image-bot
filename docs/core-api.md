# Core API

## GenerationRequest / GeneratedMedia

```python
req = GenerationRequest(
    prompt="neon cat on a roof",
    kind=MediaKind.IMAGE,
    user_id=123,
    chat_id=-100123,              # None in private chat
    resolution=Resolution.LAND,
    style="cyberpunk",
    reference_images=(b"...",),   # edit mode
)
media, remaining = await core.image.generate(req)   # or .edit(req)
```

## MediaProvider protocol

```python
class MediaProvider(Protocol):
    name: str
    supported_kinds: frozenset[MediaKind]
    async def generate(request, *, timeout=180.0) -> GeneratedMedia: ...
    async def edit(request, *, timeout=180.0) -> GeneratedMedia: ...
```

Provider errors are semantic, not HTTP: `ProviderError.RateLimited`,
`.ContentRejected`, `.Transient`, `.Fatal`. The Telegram layer maps them
to human copy (see telegram-ux.md) — never to tracebacks.

## Limiter

`Limiter.check_and_consume(user_id, chat_id, unit)` — single transaction:
check daily/hourly/user + daily/chat windows, then record usage. Raises
`QuotaExceeded` with a scope and `retry_after_seconds`.

## Storage protocol

Key methods: `ensure_user`, `user_locale`, `chat_enabled`,
`set_chat_setting`, `usage_count`, `record_usage`, `save_generation`,
`recent_generations`, `last_media_file_id`. Implementation: SqliteStorage
(append-only `usage_events`, window math by timestamp).

## i18n

`I18n.t(locale, key, **kwargs)`. All strings live in
`core/i18n/messages.py` — one tone of voice, ru/en, no exceptions in handlers.

# Architecture

## Layers

```
tgbot  (aiogram)      ← the only layer that knows Telegram exists
  └─ flows, handlers, ui

core   (pure domain)  ← knows nothing about Telegram
  ├─ types            domain language: Request, Media, Quota
  ├─ providers        adapters to generation APIs (Pollinations, …)
  ├─ image/text/video/tts services   use-cases per modality
  ├─ prompting        styles, prompt enhancement
  ├─ mcp              text AI → tools (generate, edit, enhance)
  ├─ ratelimit        our own quotas, before the provider's
  ├─ storage          SQLite (aiosqlite), protocol-first
  └─ i18n             ru/en strings, single source of tone
```

## Rules (enforced by review)

1. **No aiogram in core.** If a core module needs chat context, it takes
   `user_id`/`chat_id` as ints, never Telegram objects.
2. **No HTTP in tgbot.** Handlers call `CoreContainer` services; they never
   import `httpx` or provider classes.
3. **One composition point.** `CoreContainer` is the only place where
   providers, storage and limits are wired. Everything else receives
   dependencies (SOLID-D).
4. **Protocols over classes.** `Storage` and `MediaProvider` are
   `typing.Protocol` — swap implementations without touching consumers.

## Why this split

- Reuse: the same core can later drive Discord/HTTP UI without changes.
- Testability: services are testable with in-memory fakes of the protocols.
- Provider churn: image APIs change often; adapters are quarantined in
  `providers/`.

# API ядра

## GenerationRequest / GeneratedMedia

```python
req = GenerationRequest(
    prompt="неоновый кот на крыше",
    kind=MediaKind.IMAGE,
    user_id=123,
    chat_id=-100123,              # None в личке
    resolution=Resolution.LAND,
    style="cyberpunk",
    reference_images=(b"...",),   # режим правки
)
media, remaining = await core.image.generate(req)   # или .edit(req)
```

## Протокол MediaProvider

```python
class MediaProvider(Protocol):
    name: str
    supported_kinds: frozenset[MediaKind]
    async def generate(request, *, timeout=180.0) -> GeneratedMedia: ...
    async def edit(request, *, timeout=180.0) -> GeneratedMedia: ...
```

Ошибки провайдера семантические, не HTTP: `ProviderError.RateLimited`,
`.ContentRejected`, `.Transient`, `.Fatal`. Слой Telegram переводит их
в человеческие тексты (см. telegram-ux.md), но никогда — в traceback.

## Limiter

`Limiter.check_and_consume(user_id, chat_id, unit)` — одна транзакция:
проверка окон день/час/юзер и день/чат, затем списание. Кидает
`QuotaExceeded` со скоупом и `retry_after_seconds`.

## Протокол Storage

Ключевые методы: `ensure_user`, `user_locale`, `chat_enabled`,
`set_chat_setting`, `usage_count`, `record_usage`, `save_generation`,
`recent_generations`, `last_media_file_id`. Реализация: SqliteStorage
(журнал `usage_events` append-only, окна считаются по timestamp).

## i18n

`I18n.t(locale, key, **kwargs)`. Все строки — в `core/i18n/messages.py`:
единый тон, ru/en, никаких текстов в хендлерах.

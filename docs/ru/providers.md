# Провайдеры: вариативность

Один адаптер — много провайдеров. Межу инсталляциями меняются **данные**, не код.

## Как описан провайдер

`ProviderSpec` (core/providers/registry.py) объявляет:

- `base_url` — поддерживает `${VAR}` интерполяцию из env
- `endpoints` — пути `generate`, `edit`, `chat`, `models`; настраиваются
- `kinds` — какие модальности обслуживает
- `auth_mode` — одна из трёх стратегий (ниже)
- имена моделей — тоже интерполируются

## Три стратегии авторизации (паттерн Goose)

| Режим | Как работает | Кто использует |
|---|---|---|
| `api_key` | статический ключ из `api_key_env` | Pollinations, любые OpenAI-совместимые |
| `session` | токен web-сессии подписки + реактивный refresh (по 401); кэш в памяти | Grok Build, Gemini OAuth |
| `command` | внешний процесс выдаёт креды; кэш `refresh_interval` секунд; `0` = только реактивно (конвенция Codex) | подписка ChatGPT/Codex |

Refresh сессии **ленивый**: только при близости к истечению (leeway 300 c)
или после ошибки аутентификации — никогда по таймеру на каждый запрос.

## Выбор провайдеров

```ini
IMAGE_PROVIDER=pollinations      # бесплатно, ключ не обязателен
TEXT_PROVIDER=codex_subscription  # твоя подписка ChatGPT Plus
```

Картинки и текст выбираются **независимо**: один сервис рисует через
бесплатный API, а текст крутится на подписке.

## Встроенные спеки

- `pollinations` — бесплатная платформа, ключ опционален
- `openai_compatible_image` / `openai_compatible_text` — любой API
  OpenAI-формы: base URL и модели полностью настраиваются
- `grok_build` — план xAI Grok Build (подписка, не API-ключ)
- `codex_subscription` — сессия ChatGPT Plus/Pro через команду кредов
- `gemini_oauth` — OAuth-сессия Google-аккаунта

## Семантика ошибок и ретраи

Любая HTTP-ошибка становится типизированной (`RateLimited`, `ContentRejected`,
`InvalidValue`, `Authentication`, `CreditsExhausted`, `Transient`) — никогда
сырым статус-кодом. Ретраи: экспоненциальный backoff (1 c, ×2, потолок 30 c)
с jitter 0.8-1.2× против thundering herd; `Retry-After` от 429 (секунды или
HTTP-date, потолок 1 ч) перекрывает вычисленную задержку. Фатальные ошибки
(авторизация, кредиты) не ретраятся вовсе.

## Добавить провайдера

Одна запись в `BUILTIN_SPECS`. Если формат провайдера совпадает с существующим
(OpenAI images / OpenAI chat / Pollinations GET) — ноль нового кода.

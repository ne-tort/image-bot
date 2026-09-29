# Развёртывание

## Docker Compose

```bash
cp .env.example .env
# вписать BOT_TOKEN
docker compose up -d
```

- Один сервис, polling (Docker Desktop за NAT — честный дефолт).
- SQLite в volume `./data:/data`.
- Healthcheck пингует Telegram getMe.

## Разовая настройка в Telegram

1. @BotFather → /newbot → токен в `.env`.
2. **/setprivacy → Disable** — обязательно для группового UX.
3. Добавить бота в группу: он здоровается и включает себя сам.

## Подписка Grok Build (опционально)

Поставь `IMAGE_PROVIDER=grok_build` + `BOT_OWNER_ID`, отправь `/login` боту
в личку и пройди device-code вход (детали:
[providers.md](providers.md#xai-grok-build-вход-по-подписке-в-docker)).
Сессия хранится в volume `/data` и переживает рестарты.

## Переменные окружения

См. `.env.example` в корне репо. У всего есть дефолты, кроме `BOT_TOKEN`.

## Логи

`docker compose logs -f bot`. Уровень: `LOG_LEVEL=DEBUG`.

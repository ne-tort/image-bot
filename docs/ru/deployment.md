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

## Переменные окружения

См. `.env.example` в корне репо. У всего есть дефолты, кроме `BOT_TOKEN`.

## Логи

`docker compose logs -f bot`. Уровень: `LOG_LEVEL=DEBUG`.

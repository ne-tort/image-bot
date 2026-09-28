# Deployment

## Docker Compose

```bash
cp .env.example .env
# set BOT_TOKEN
docker compose up -d
```

- Single service, polling (Docker Desktop behind NAT — honest default).
- SQLite in named volume `./data:/data`.
- Healthcheck pokes Telegram getMe.

## One-time Telegram setup

1. @BotFather → /newbot → token to `.env`.
2. **/setprivacy → Disable** — required for group UX.
3. Add bot to a group; it greets and enables itself.

## Env reference

See `.env.example` at repo root. Everything has a sane default except
`BOT_TOKEN`.

## Logs

`docker compose logs -f bot`. Log level via `LOG_LEVEL=DEBUG`.

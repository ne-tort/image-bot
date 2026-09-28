# Roadmap

## v0.2 — image polish
- Media-group (album) aggregation for edit (Eugene job-queue pattern)
- `/history` inline gallery with file_id reuse
- Seed control + "same seed, new prompt" flow
- Retry with backoff on ProviderError.Transient

## v0.3 — text & MCP loop
- Full tool-use loop in TextService (multi-turn, TOOL protocol)
- Persistent dialog memory per user (storage: `messages` table)
- Prompt suggestions from history

## v0.4 — video & TTS
- VideoService: async job → progress → send as video note or file
- TTSService: /say command, voice replies

## v0.5 — ops
- Webhook mode (public URL), structured JSON logs
- /admin for owner: stats, broadcast
- Optional per-user API keys (PromptArt pattern)
- Postgres profile for large deployments

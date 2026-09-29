from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Optional, Sequence

import aiosqlite

from core.types import GeneratedMedia


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    locale      TEXT NOT NULL DEFAULT 'ru',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chats (
    chat_id     INTEGER PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id     INTEGER NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    PRIMARY KEY (chat_id, key)
);
CREATE TABLE IF NOT EXISTS usage_events (
    user_id     INTEGER NOT NULL,
    chat_id     INTEGER,
    unit        TEXT NOT NULL,
    ts          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_user_ts ON usage_events (user_id, unit, ts);
CREATE INDEX IF NOT EXISTS idx_usage_chat_ts ON usage_events (chat_id, unit, ts);
CREATE TABLE IF NOT EXISTS generations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    chat_id     INTEGER,
    kind        TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    model       TEXT NOT NULL,
    file_id     TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS original_prompts (
    user_id     INTEGER PRIMARY KEY,
    prompt      TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS last_prompts (
    user_id     INTEGER PRIMARY KEY,
    prompt      TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);
"""


async def _migrate_legacy_prompt_tables(conn) -> None:
    """original_prompts (id PK, несколько строк) → (user_id PK, одна строка).

    Docker volume живёт долго; схема меняется — мигрируем тихо.
    """
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='original_prompts'"
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return
    async with conn.execute("PRAGMA table_info(original_prompts)") as cur:
        cols = [r[1] for r in await cur.fetchall()]
    if "id" in cols:  # старая схема: пересоздаст SCHEMA с user_id PK
        await conn.execute("DROP TABLE original_prompts")


class SqliteStorage:
    """Единственная реализация Storage. Дешёвая, честная, в volume /data.

   usage_events — append-only журнал; окна считаются по ts.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await _migrate_legacy_prompt_tables(self._conn)
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    # ── users / chats ─────────────────────────────────────
    async def ensure_user(self, user_id: int, locale: str = "ru") -> None:
        await self._conn.execute(
            "INSERT INTO users (user_id, locale, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id) DO NOTHING",
            (user_id, locale, _now_iso()),
        )
        await self._conn.commit()

    async def user_locale(self, user_id: int) -> str:
        row = await self._fetchone("SELECT locale FROM users WHERE user_id = ?", (user_id,))
        return row["locale"] if row else "ru"

    async def set_user_locale(self, user_id: int, locale: str) -> None:
        await self._exec("UPDATE users SET locale = ? WHERE user_id = ?", (locale, user_id))

    async def user_stats(self, user_id: int) -> dict:
        row = await self._fetchone(
            "SELECT COUNT(*) AS total FROM generations WHERE user_id = ?", (user_id,)
        )
        return {"generations": row["total"]}

    async def ensure_chat(self, chat_id: int, title: str = "") -> None:
        await self._conn.execute(
            "INSERT INTO chats (chat_id, title, enabled, created_at) VALUES (?, ?, 1, ?) "
            "ON CONFLICT (chat_id) DO UPDATE SET title = excluded.title",
            (chat_id, title, _now_iso()),
        )
        await self._conn.commit()

    async def chat_enabled(self, chat_id: int) -> bool:
        row = await self._fetchone("SELECT enabled FROM chats WHERE chat_id = ?", (chat_id,))
        return bool(row and row["enabled"])

    async def set_chat_enabled(self, chat_id: int, enabled: bool) -> None:
        await self._exec(
            "UPDATE chats SET enabled = ? WHERE chat_id = ?", (int(enabled), chat_id)
        )

    # ── chat settings ─────────────────────────────────────
    async def chat_setting(self, chat_id: int, key: str) -> str:
        row = await self._fetchone(
            "SELECT value FROM chat_settings WHERE chat_id = ? AND key = ?", (chat_id, key)
        )
        return row["value"] if row else ""

    async def set_chat_setting(self, chat_id: int, key: str, value: str) -> None:
        await self._conn.execute(
            "INSERT INTO chat_settings (chat_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT (chat_id, key) DO UPDATE SET value = excluded.value",
            (chat_id, key, value),
        )
        await self._conn.commit()

    # ── usage ─────────────────────────────────────────────
    async def usage_count(self, user_id: int, unit: str, window: str) -> int:
        since = _window_start(window)
        row = await self._fetchone(
            "SELECT COUNT(*) AS n FROM usage_events WHERE user_id = ? AND unit = ? AND ts >= ?",
            (user_id, unit, since),
        )
        return row["n"]

    async def chat_usage_count(self, chat_id: int, unit: str, window: str) -> int:
        since = _window_start(window)
        row = await self._fetchone(
            "SELECT COUNT(*) AS n FROM usage_events WHERE chat_id = ? AND unit = ? AND ts >= ?",
            (chat_id, unit, since),
        )
        return row["n"]

    async def record_usage(self, user_id: int, chat_id: int | None, unit: str) -> None:
        await self._exec(
            "INSERT INTO usage_events (user_id, chat_id, unit, ts) VALUES (?, ?, ?, ?)",
            (user_id, chat_id, unit, int(time.time())),
        )

    async def window_seconds_left(self, window: str) -> int:
        start = _window_start(window)
        now = int(time.time())
        span = 86400 if window == "day" else 3600
        return max(0, start + span - now)

    # ── generations history ───────────────────────────────
    async def save_generation(self, user_id: int, chat_id: int | None, media: GeneratedMedia, file_id: str = "") -> None:
        await self._exec(
            "INSERT INTO generations (user_id, chat_id, kind, prompt, model, file_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, chat_id, media.kind.value, media.prompt, media.model, file_id, _now_iso()),
        )

    async def recent_generations(self, user_id: int, limit: int = 8) -> Sequence[dict]:
        rows = await self._fetchall(
            "SELECT kind, prompt, file_id, created_at FROM generations "
            "WHERE user_id = ? AND file_id IS NOT NULL ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(r) for r in rows]

    async def last_media_file_id(self, user_id: int) -> Optional[str]:
        row = await self._fetchone(
            "SELECT file_id FROM generations WHERE user_id = ? AND kind = 'image' "
            "ORDER BY id DESC LIMIT 1", (user_id,),
        )
        return row["file_id"] if row and row["file_id"] else None

    async def save_original_prompt(self, user_id: int, prompt: str) -> None:
        await self._save_one_prompt("original_prompts", user_id, prompt)

    async def save_last_prompt(self, user_id: int, prompt: str) -> None:
        await self._save_one_prompt("last_prompts", user_id, prompt)

    async def _save_one_prompt(self, table: str, user_id: int, prompt: str) -> None:
        """Одна таблица — одна строка на юзера (upsert)."""
        await self._exec(
            f"INSERT INTO {table} (user_id, prompt, created_at) VALUES (?, ?, unixepoch()) "
            f"ON CONFLICT(user_id) DO UPDATE SET prompt = excluded.prompt, created_at = unixepoch()",
            (user_id, prompt),
        )

    async def last_prompt(self, user_id: int) -> Optional[str]:
        row = await self._fetchone(
            "SELECT prompt FROM last_prompts WHERE user_id = ?", (user_id,),
        )
        return row["prompt"] if row else None

    async def original_prompt(self, user_id: int) -> Optional[str]:
        row = await self._fetchone(
            "SELECT prompt FROM original_prompts WHERE user_id = ?",
            (user_id,),
        )
        return row["prompt"] if row else None

    async def set_last_media_file_id(self, user_id: int, file_id: str) -> None:
        await self._exec(
            "UPDATE generations SET file_id = ? WHERE id = "
            "(SELECT id FROM generations WHERE user_id = ? AND kind = 'image' ORDER BY id DESC LIMIT 1)",
            (file_id, user_id),
        )

    # ── helpers ────────────────────────────────────────────
    async def _exec(self, sql: str, params: tuple) -> None:
        await self._conn.execute(sql, params)
        await self._conn.commit()

    async def _fetchone(self, sql: str, params: tuple):
        cur = await self._conn.execute(sql, params)
        return await cur.fetchone()

    async def _fetchall(self, sql: str, params: tuple):
        cur = await self._conn.execute(sql, params)
        return await cur.fetchall()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _window_start(window: str) -> int:
    now = int(time.time())
    if window == "day":
        return now - (now % 86400)
    return now - (now % 3600)

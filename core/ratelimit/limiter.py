from __future__ import annotations
from dataclasses import dataclass

from core.storage.repository import Storage


@dataclass(frozen=True, slots=True)
class LimitProfile:
    """Свои лимиты — до провайдера. На юзера и на чат отдельно."""
    per_user_daily: int
    per_user_hourly: int
    per_chat_daily: int


@dataclass(slots=True)
class Verdict:
    allowed: bool
    scope: str = ""
    retry_after_seconds: int = 0
    remaining: int = 0


class Limiter:
    """Счётчик-окно на сутки/час. Проверка и списание — одна транзакция.

    DIP: зависит от протокола Storage, не от SQLite.
    """

    def __init__(self, storage: Storage, profile: LimitProfile):
        self._storage = storage
        self._profile = profile

    async def check_and_consume(self, user_id: int, chat_id: int | None, unit: str) -> Verdict:
        p = self._profile
        # чат и юзер считаются по одному и тому же unit
        used_user_day = await self._storage.usage_count(user_id, unit, window="day")
        if used_user_day >= p.per_user_daily:
            return Verdict(False, f"daily_{unit}", retry_after_seconds=await self._storage.window_seconds_left("day"))
        used_user_hour = await self._storage.usage_count(user_id, unit, window="hour")
        if used_user_hour >= p.per_user_hourly:
            return Verdict(False, f"hourly_{unit}", retry_after_seconds=await self._storage.window_seconds_left("hour"))
        if chat_id is not None:
            used_chat = await self._storage.chat_usage_count(chat_id, unit, window="day")
            if used_chat >= p.per_chat_daily:
                return Verdict(False, f"chat_daily_{unit}", retry_after_seconds=await self._storage.window_seconds_left("day"))
        await self._storage.record_usage(user_id, chat_id, unit)
        remaining = p.per_user_daily - used_user_day - 1
        return Verdict(True, remaining=remaining)

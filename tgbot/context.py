from __future__ import annotations
from dataclasses import dataclass

from aiogram import Router

from core.container import CoreContainer
from core.i18n import I18n


@dataclass(slots=True)
class BotContext:
    """Всё, что нужно хендлеру. Собирается один раз в main.

    dataclass, а не глобал: тестируемо, потокобезопасно, DI-явный.
    """
    core: CoreContainer
    i18n: I18n
    owner_id: int | None
    router: Router

    def tr(self, locale: str, key: str, **kw) -> str:
        return self.i18n.t(locale, key, **kw)

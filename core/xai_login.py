from __future__ import annotations
from pathlib import Path

from core.providers.xai_oauth import Session, XaiOAuthClient


class XaiLoginService:
    """Мост между device-flow и провайдером.

    Session из /data переживает рестарт контейнера; при сборке CoreContainer
    она подставляется как SessionToken → Authorization: Bearer.
    """

    def __init__(self, session_path: Path, http=None):
        self._client = XaiOAuthClient(session_path, http)

    @property
    def client(self) -> XaiOAuthClient:
        return self._client

    def load_session(self) -> Session | None:
        return self._client.load_session()

    def has_session(self) -> bool:
        s = self._client.load_session()
        return bool(s and s.access_token)

    def clear(self) -> None:
        self._client.clear_session()

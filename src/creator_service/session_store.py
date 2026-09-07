from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class ServerSession:
    user_id: str
    upstream_session_id: str
    expires_at: datetime


class SessionStore:
    def __init__(self, lifetime: timedelta = timedelta(hours=8)) -> None:
        self._lifetime = lifetime
        self._sessions: dict[str, ServerSession] = {}
        self._lock = threading.Lock()

    def issue(self, user_id: str, upstream_session_id: str) -> str:
        session_key = secrets.token_urlsafe(32)
        session = ServerSession(
            user_id=user_id,
            upstream_session_id=upstream_session_id,
            expires_at=datetime.now(UTC) + self._lifetime,
        )
        with self._lock:
            self._sessions[session_key] = session
        return session_key

    def resolve(self, session_key: str | None) -> ServerSession | None:
        if not session_key:
            return None
        with self._lock:
            session = self._sessions.get(session_key)
            if session and session.expires_at > datetime.now(UTC):
                return session
            self._sessions.pop(session_key, None)
        return None

    def revoke(self, session_key: str | None) -> None:
        if session_key:
            with self._lock:
                self._sessions.pop(session_key, None)


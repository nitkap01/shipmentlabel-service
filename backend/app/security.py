"""Admin authentication (D14).

Single shared password from ADMIN_PASSWORD, compared with a constant-time
comparison (hmac.compare_digest) to avoid a timing oracle. On success, a
JWT (HS256, signed with SESSION_SECRET) is issued in an HttpOnly,
SameSite=Lax cookie. There are no per-user accounts and no sessions table:
the only "log everyone out" lever is rotating SESSION_SECRET, which is
sufficient for one shared password used by one business.

The Next.js `middleware.ts` cookie-presence check is a UX redirect only.
This module is the actual security boundary — every protected backend
route depends on `require_admin`, which re-verifies the JWT on every
request.

A small in-memory lockout blunts online brute force. It is intentionally
in-process (not shared across replicas) since this app runs as a single
backend container.
"""

import hmac
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Cookie, HTTPException, status

from app.config import settings

COOKIE_NAME = "session"
_JWT_ALGORITHM = "HS256"
_JWT_SUBJECT = "admin"

_failed_attempts: dict[str, list[float]] = {}


class LockedOutError(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds


def _client_bucket(client_key: str) -> list[float]:
    return _failed_attempts.setdefault(client_key, [])


def check_lockout(client_key: str) -> None:
    now = time.monotonic()
    window_start = now - settings.login_lockout_seconds
    attempts = [t for t in _client_bucket(client_key) if t >= window_start]
    _failed_attempts[client_key] = attempts
    if len(attempts) >= settings.login_lockout_attempts:
        retry_after = int(attempts[0] + settings.login_lockout_seconds - now)
        raise LockedOutError(max(retry_after, 1))


def record_failed_attempt(client_key: str) -> None:
    _client_bucket(client_key).append(time.monotonic())


def clear_attempts(client_key: str) -> None:
    _failed_attempts.pop(client_key, None)


def verify_password(candidate: str) -> bool:
    return hmac.compare_digest(candidate.encode(), settings.admin_password.encode())


def issue_session_token() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": _JWT_SUBJECT,
        "iat": now,
        "exp": now + timedelta(hours=settings.session_hours),
    }
    return jwt.encode(payload, settings.session_secret, algorithm=_JWT_ALGORITHM)


def verify_session_token(token: str) -> bool:
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError:
        return False
    return payload.get("sub") == _JWT_SUBJECT


def require_admin(session: str | None = Cookie(default=None)) -> None:
    if not session or not verify_session_token(session):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

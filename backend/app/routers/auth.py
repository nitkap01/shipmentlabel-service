from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.config import settings
from app.schemas import LoginRequest
from app.security import (
    COOKIE_NAME,
    LockedOutError,
    check_lockout,
    clear_attempts,
    issue_session_token,
    record_failed_attempt,
    verify_password,
    verify_session_token,
)

router = APIRouter()


@router.post("/auth/login")
async def login(payload: LoginRequest, response: Response):
    client_key = "admin"  # single shared admin: one bucket is correct, not a placeholder for more
    try:
        check_lockout(client_key)
    except LockedOutError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Try again in {exc.retry_after_seconds}s.",
        )

    if not verify_password(payload.password):
        record_failed_attempt(client_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")

    clear_attempts(client_key)
    token = issue_session_token()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_hours * 3600,
    )
    return {"authenticated": True}


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"authenticated": False}


@router.get("/auth/me")
async def me(session: str | None = Cookie(default=None)):
    return {"authenticated": bool(session and verify_session_token(session))}

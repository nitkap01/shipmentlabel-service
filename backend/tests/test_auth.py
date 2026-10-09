import jwt

from app.security import COOKIE_NAME, issue_session_token


def test_wrong_password_returns_401_and_no_cookie(client):
    resp = client.post("/api/auth/login", json={"password": "wrong"})
    assert resp.status_code == 401
    assert COOKIE_NAME not in resp.cookies


def test_correct_password_sets_httponly_samesite_cookie(client):
    resp = client.post("/api/auth/login", json={"password": "test-admin-password-0123"})
    assert resp.status_code == 200
    assert resp.json() == {"authenticated": True}
    set_cookie_header = resp.headers.get("set-cookie", "")
    assert "httponly" in set_cookie_header.lower()
    assert "samesite=lax" in set_cookie_header.lower()


def test_protected_route_without_cookie_returns_401(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 401


def test_protected_route_with_valid_cookie_succeeds(logged_in_client):
    resp = logged_in_client.get("/api/settings")
    assert resp.status_code == 200


def test_tampered_token_rejected(client):
    client.cookies.set(COOKIE_NAME, "not-a-real-jwt")
    resp = client.get("/api/settings")
    assert resp.status_code == 401


def test_expired_token_rejected(client):
    import datetime

    from app.config import settings as app_settings

    expired_payload = {
        "sub": "admin",
        "iat": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=13),
        "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1),
    }
    expired_token = jwt.encode(expired_payload, app_settings.session_secret, algorithm="HS256")
    client.cookies.set(COOKIE_NAME, expired_token)
    resp = client.get("/api/settings")
    assert resp.status_code == 401


def test_token_signed_with_wrong_secret_rejected(client):
    bad_token = jwt.encode({"sub": "admin"}, "wrong-secret", algorithm="HS256")
    client.cookies.set(COOKIE_NAME, bad_token)
    resp = client.get("/api/settings")
    assert resp.status_code == 401


def test_lockout_after_repeated_failures(client):
    from app.security import _failed_attempts

    _failed_attempts.clear()
    for _ in range(5):
        client.post("/api/auth/login", json={"password": "wrong"})
    resp = client.post("/api/auth/login", json={"password": "wrong"})
    assert resp.status_code == 429
    _failed_attempts.clear()


def test_logout_clears_cookie(logged_in_client):
    resp = logged_in_client.post("/api/auth/logout")
    assert resp.status_code == 200
    me = logged_in_client.get("/api/auth/me")
    assert me.json() == {"authenticated": False}


def test_valid_token_helper_round_trips():
    token = issue_session_token()
    from app.security import verify_session_token

    assert verify_session_token(token) is True

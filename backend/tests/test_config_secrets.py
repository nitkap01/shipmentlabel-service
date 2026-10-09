"""SHIP-4: the app must refuse to start without a strong ADMIN_PASSWORD and SESSION_SECRET (no built-in defaults)."""
import pytest
from pydantic import ValidationError

from app.config import Settings

GOOD_PW = "Xk3-v9Lq2mR7tW8y"            # 16 characters
GOOD_SECRET = "s" * 32


def make(**env):
    # _env_file=None: ignore any local .env so only the values given here count
    return Settings(_env_file=None, **env)


def test_strong_values_accepted():
    s = make(admin_password=GOOD_PW, session_secret=GOOD_SECRET)
    assert s.admin_password == GOOD_PW


@pytest.mark.parametrize("env", [
    {},                                                        # nothing set: no defaults any more
    {"session_secret": GOOD_SECRET},                           # password missing
    {"admin_password": GOOD_PW},                               # secret missing
    {"admin_password": "changeme", "session_secret": GOOD_SECRET},
    {"admin_password": "short-pw", "session_secret": GOOD_SECRET},
    {"admin_password": GOOD_PW, "session_secret": "dev-secret-change-me"},
    {"admin_password": GOOD_PW, "session_secret": "too-short-secret"},
])
def test_missing_or_weak_values_refused(env, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(ValidationError):
        make(**env)

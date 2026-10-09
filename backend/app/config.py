from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# SHIP-4: no built-in admin password or session secret. Both must come from the
# environment (.env), and weak or placeholder values are refused at startup, so a
# server can never come up with a guessable login or a forgeable session cookie.
ADMIN_PASSWORD_MIN = 16
SESSION_SECRET_MIN = 32
_PLACEHOLDERS = {"changeme", "change-me", "dev-secret-change-me", "password", "admin", "secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://nitinkapoor@localhost:5432/shipmentlabel"

    epg_api_key_sandbox: str | None = None
    epg_api_key_production: str | None = None

    admin_password: str  # required: ADMIN_PASSWORD, at least 16 characters
    session_secret: str  # required: SESSION_SECRET, at least 32 characters
    session_hours: int = 12
    cookie_secure: bool = False

    label_storage_root: str = "/data"
    label_pdf_dpi_fallback: int = 203

    app_timezone: str = "America/New_York"
    bulk_max_rows: int = 500

    login_lockout_attempts: int = 5
    login_lockout_seconds: int = 300

    # Local dev (running from a repo checkout): db.py falls back to
    # <repo_root>/migrations when this is unset. In Docker the image layout
    # doesn't mirror the repo, so the container sets this explicitly.
    migrations_dir: str | None = None

    @field_validator("admin_password")
    @classmethod
    def _strong_admin_password(cls, v: str) -> str:
        if v.strip().lower() in _PLACEHOLDERS or len(v) < ADMIN_PASSWORD_MIN:
            raise ValueError(
                f"ADMIN_PASSWORD must be set in .env and be at least {ADMIN_PASSWORD_MIN} characters "
                "(generate one: python3 -c \"import secrets; print(secrets.token_urlsafe(18))\")"
            )
        return v

    @field_validator("session_secret")
    @classmethod
    def _strong_session_secret(cls, v: str) -> str:
        if v.strip().lower() in _PLACEHOLDERS or len(v) < SESSION_SECRET_MIN:
            raise ValueError(
                f"SESSION_SECRET must be set in .env and be at least {SESSION_SECRET_MIN} characters "
                "(generate one: python3 -c \"import secrets; print(secrets.token_urlsafe(48))\")"
            )
        return v


settings = Settings()

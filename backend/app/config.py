from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://nitinkapoor@localhost:5432/shipmentlabel"

    epg_api_key_sandbox: str | None = None
    epg_api_key_production: str | None = None

    admin_password: str = "changeme"
    session_secret: str = "dev-secret-change-me"
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


settings = Settings()

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

# NullPool: this is a single shared-admin internal tool with negligible
# concurrency, so pooling buys nothing. It also sidesteps a real failure
# mode where a pooled asyncpg connection created on one asyncio event loop
# is later checked out on a different loop (this happens routinely in the
# test suite, which mixes pytest-asyncio's loop with TestClient's own
# internal loop) — asyncpg raises "attached to a different loop" in that
# case. NullPool opens a fresh connection per checkout, so no connection
# ever crosses a loop boundary.
engine = create_async_engine(settings.database_url, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

MIGRATIONS_DIR = (
    Path(settings.migrations_dir)
    if settings.migrations_dir
    else Path(__file__).resolve().parent.parent.parent / "migrations"
)


async def get_db():
    async with SessionLocal() as session:
        yield session


async def run_migrations() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
        )
        applied = {
            row[0]
            for row in (await conn.execute(text("SELECT filename FROM schema_migrations"))).all()
        }

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            sql = path.read_text()
            statements = [s.strip() for s in sql.split(";") if s.strip()]
            for statement in statements:
                await conn.execute(text(statement))
            await conn.execute(
                text("INSERT INTO schema_migrations (filename) VALUES (:filename)"),
                {"filename": path.name},
            )

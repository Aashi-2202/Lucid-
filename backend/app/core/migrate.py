"""Initialize missing MVP tables and apply versioned upgrades: python -m app.core.migrate."""
import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from app.core.database import Base, engine
from app.core.config import settings
import app.models  # noqa: F401


def upgrade_connection(connection):
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql("SET LOCAL lock_timeout = '10s'")
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(1392810522)")
    Base.metadata.create_all(connection)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def main():
    url = make_url(settings.database_direct_url) if settings.database_direct_url else engine.url
    # Same supplied Neon endpoint/role/password, without its pooler suffix.
    if url.host and url.host.endswith(".neon.tech") and "-pooler." in url.host:
        url = url.set(host=url.host.replace("-pooler.", "."))
    migration_engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
    try:
        async with migration_engine.begin() as connection:
            await connection.run_sync(upgrade_connection)
        print("Database migration complete: 0001_password_accounts.")
    finally:
        await migration_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

"""Share the application's async connection without printing its credentials."""
import asyncio

from alembic import context
from app.core.database import Base, engine
import app.models  # noqa: F401 - register metadata


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async():
    async with engine.begin() as connection:
        await connection.run_sync(run)
    await engine.dispose()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    asyncio.run(run_async())

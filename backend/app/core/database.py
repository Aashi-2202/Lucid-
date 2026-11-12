"""Database engine and session factory."""

from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import inspect

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True, hide_parameters=True)

async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_tables():
    """Create all tables. Used at startup for the MVP."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        columns = await conn.run_sync(lambda connection: {c["name"] for c in inspect(connection).get_columns("recruiters")})
        if not {"username", "password_hash"} <= columns:
            raise RuntimeError("Database upgrade required. Run python -m app.core.migrate from backend before starting Lucid.")

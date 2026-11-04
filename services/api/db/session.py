"""Database session management.

Schema is managed exclusively by Alembic migrations.
Run `alembic upgrade head` before starting the API for the first time
or after pulling new migrations.

Do NOT call Base.metadata.create_all() here — it bypasses migration
tracking and causes schema drift on existing deployments.
"""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./blackbox.db")

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("APP_ENV") == "development",
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Verify the database engine is reachable at startup.

    Schema creation and migrations are handled by Alembic, not here.
    Run ``alembic upgrade head`` before starting the server on a new
    deployment or after pulling new migration files.
    """
    # Lightweight connectivity check only — no DDL.
    async with engine.connect() as conn:
        await conn.run_sync(lambda c: None)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

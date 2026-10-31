"""
services/worker/db.py
──────────────────────
Synchronous SQLAlchemy session for Celery workers.
Workers run in a separate process and cannot use the async session
used by FastAPI.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

_DATABASE_URL = (
    os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./blackbox.db")
    .replace("sqlite+aiosqlite", "sqlite")
    .replace("postgresql+asyncpg", "postgresql+psycopg")
)

_engine = create_engine(
    _DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in _DATABASE_URL else {},
    pool_pre_ping=True,
)

_SessionLocal = sessionmaker(bind=_engine, autoflush=True, autocommit=False)


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

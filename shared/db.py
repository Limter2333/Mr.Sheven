"""Database engine and session factory."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from shared.config import config

engine = create_engine(
    config.mysql.url,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    echo=(config.env == "development"),
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a DB session, auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
"""PostgreSQL async connection and session management.

Provides get_async_engine() and get_async_session() helpers.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from memora.core.config import get_settings


def get_async_engine():
    """Return async SQLAlchemy engine configured from Settings."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
    )


def get_async_session(engine) -> AsyncSession:
    """Return a new async session."""
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return async_session()
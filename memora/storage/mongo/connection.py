"""
storage/mongo/connection.py

Motor async MongoDB Atlas client factory.
Single client instance per process — Motor manages its own connection pool.
All collections are accessed through get_database().

Usage:
    from memora.storage.mongo.connection import get_database
    db = await get_database()
    collection = db["mem_cubes"]
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from memora.core.errors import StorageConnectionError

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def init_motor(mongodb_url: str, db_name: str) -> None:
    """
    Initialize the Motor client and database reference.
    Call this once during app startup (api/app.py lifespan).

    Args:
        mongodb_url:  Full Atlas connection string from settings.mongodb_url
        db_name:      Database name from settings.mongodb_db_name

    Raises:
        StorageConnectionError: if the Atlas ping fails (wrong URL, bad credentials)
    """
    global _client, _db
    try:
        _client = AsyncIOMotorClient(
            mongodb_url,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
        )
        # Ping to verify connection before proceeding
        await _client.admin.command("ping")
        _db = _client[db_name]
    except Exception as e:
        raise StorageConnectionError(
            f"MongoDB Atlas connection failed: {e}. "
            f"Check MONGODB_URL in .env"
        ) from e


async def get_database() -> AsyncIOMotorDatabase:
    """
    Return the active Motor database instance.
    Raises StorageConnectionError if init_motor() was not called first.
    """
    if _db is None:
        raise StorageConnectionError(
            "MongoDB not initialized. Call init_motor() in app lifespan first."
        )
    return _db


async def dispose_motor() -> None:
    """
    Close the Motor client. Call during app shutdown.
    """
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None

"""Seed demo data for MEMORA presentations."""

from __future__ import annotations

import asyncio

from memora.core.config import get_settings
from memora.storage.vector.embedding import SentenceTransformerEmbedder
from memora.vault.mem_cube import MemCubeFactory


async def main() -> None:
    """Seed deterministic demo-memory counts for local demo mode."""
    settings = get_settings()

    from memora.storage.mongo.connection import init_motor, get_database, dispose_motor
    from memora.storage.mongo.collections import setup_indexes
    from memora.storage.vector.mongo_vector_client import MongoVectorClient
    from memora.core.types import MemoryType

    await init_motor(settings.mongodb_url, settings.mongodb_db_name)
    db = await get_database()
    await setup_indexes(db)

    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    mongo_client = MongoVectorClient(db, settings.embedding_dim)
    factory = MemCubeFactory(embedder, settings)

    # 1. Seed Episodic Memories
    episodic_data = [
        "User asked about the project status.",
        "Agent explained the new MongoDB migration plan.",
        "The team discussed the upcoming hackathon.",
        "User confirmed they like coffee.",
    ]
    for content in episodic_data:
        cube = await factory.create(content, MemoryType.EPISODIC, "session-123")
        await mongo_client.upsert(cube)

    # 2. Seed Semantic Memories
    semantic_data = [
        ("coffee_preference", "User prefers dark roast coffee."),
        ("project_role", "User is the lead architect for SolarisX."),
    ]
    for key, content in semantic_data:
        cube = await factory.create(content, MemoryType.SEMANTIC, "session-123", extra={"key": key})
        await mongo_client.upsert(cube)

    # 3. Seed a contradiction for demo
    conflict_cube = await factory.create(
        "User actually prefers light roast coffee.",
        MemoryType.SEMANTIC,
        "session-123",
        extra={"key": "coffee_preference"}
    )
    # We don't upsert directly; this would be caught by judge in a real flow.
    # For seeding purposes, we just ensure we have some data.
    await mongo_client.upsert(conflict_cube)

    print("SUCCESS: Demo data seeded successfully")
    print(f"  Episodic memories: {len(episodic_data)}")
    print(f"  Semantic memories: {len(semantic_data)}")
    print("  Quarantine records: 1 (simulated)")

    await dispose_motor()


if __name__ == "__main__":
    asyncio.run(main())

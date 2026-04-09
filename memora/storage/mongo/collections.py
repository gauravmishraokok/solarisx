"""
storage/mongo/collections.py

Collection name constants and Atlas index setup.
Replaces Alembic migrations — MongoDB is schemaless so no migrations needed.

Collections:
    mem_cubes          - All MemCube documents (episodic, semantic, kg_node)
    quarantine_records - Pending and resolved contradictions
    failure_log        - Negative outcome records for Experience module
    timeline_events    - Audit trail of all memory operations

Run setup_indexes() once on app startup to ensure all indexes exist.
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

# ─── Collection name constants ─────────────────────────────────────────────────
MEM_CUBES = "mem_cubes"
QUARANTINE_RECORDS = "quarantine_records"
FAILURE_LOG = "failure_log"
TIMELINE_EVENTS = "timeline_events"


async def setup_indexes(db: AsyncIOMotorDatabase) -> None:
    """
    Create all required indexes on startup.
    Safe to call on every startup — MongoDB's createIndex is idempotent.
    Does NOT create the Atlas Vector Search index (that must be done via
    Atlas UI or Atlas Admin API — see setup instructions below).
    """
    # mem_cubes indexes
    await db[MEM_CUBES].create_indexes([
        IndexModel([("memory_type", ASCENDING)]),
        IndexModel([("tier", ASCENDING)]),
        IndexModel([("tags", ASCENDING)]),
        IndexModel([("provenance.session_id", ASCENDING)]),
        IndexModel([("provenance.created_at", DESCENDING)]),
        IndexModel([("access_count", DESCENDING)]),
        IndexModel([("provenance.updated_at", DESCENDING)]),
    ])

    # quarantine_records indexes
    await db[QUARANTINE_RECORDS].create_indexes([
        IndexModel([("status", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
        IndexModel([("incoming_cube_id", ASCENDING)]),
    ])

    # failure_log indexes
    await db[FAILURE_LOG].create_indexes([
        IndexModel([("session_id", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
    ])

    # timeline_events indexes
    await db[TIMELINE_EVENTS].create_indexes([
        IndexModel([("cube_id", ASCENDING)]),
        IndexModel([("session_id", ASCENDING)]),
        IndexModel([("event_type", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
    ])


# ─── ATLAS VECTOR SEARCH INDEX SETUP ──────────────────────────────────────────
#
# The embedding_index on mem_cubes CANNOT be created programmatically
# with Motor. It must be created once via the Atlas UI or Atlas CLI.
#
# STEP-BY-STEP ATLAS UI SETUP:
# 1. Go to cloud.mongodb.com → your cluster → Browse Collections
# 2. Click "Search" tab → "Create Search Index"
# 3. Select "Atlas Vector Search" (NOT regular search)
# 4. Select database: memora, collection: mem_cubes
# 5. Paste this JSON as the index definition:
#
# {
#   "fields": [
#     {
#       "type": "vector",
#       "path": "embedding",
#       "numDimensions": 384,
#       "similarity": "cosine"
#     }
#   ]
# }
#
# 6. Name the index: embedding_index
# 7. Click Create — takes ~2 minutes to build
#
# Once created, the MongoVectorClient.similarity_search() method
# will use it automatically via $vectorSearch aggregation pipeline.
#
# YOU ONLY DO THIS ONCE. The index persists on Atlas.
# ─────────────────────────────────────────────────────────────────────────────

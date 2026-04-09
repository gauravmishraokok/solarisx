"""EpisodicRepo implements IEpisodicRepo.

Stores and retrieves episodic MemCubes with session-based queries.
"""

from typing import Optional, List
from memora.core.interfaces import IEpisodicRepo
from memora.core.types import MemCube, MemoryType
from memora.core.errors import MemoryNotFoundError, DuplicateMemoryError
from memora.vault.timeline_writer import TimelineWriter
from memora.storage.vector.mongo_vector_client import MongoVectorClient


class EpisodicRepo(IEpisodicRepo):
    """MongoDB implementation of episodic memory repository."""

    def __init__(self, vector_client: MongoVectorClient, timeline_writer: TimelineWriter):
        self.vector_client = vector_client
        self.timeline_writer = timeline_writer

    async def save(self, cube: MemCube) -> str:
        """Persist an episodic MemCube. Returns the cube.id."""
        await self.vector_client.upsert(cube)
        if self.timeline_writer:
            await self.timeline_writer.write(
                event_type="created",
                cube_id=cube.id,
                session_id=cube.provenance.session_id if cube.provenance else None,
            )
        return cube.id

    async def get(self, cube_id: str) -> Optional[MemCube]:
        """Fetch by ID. Returns None if not found."""
        from memora.storage.vector.mongo_vector_client import _doc_to_cube
        doc = await self.vector_client.collection.find_one({"_id": cube_id})
        if not doc:
            return None
        return _doc_to_cube(doc)

    async def delete(self, cube_id: str) -> None:
        """Hard delete. Raises MemoryNotFoundError if not found."""
        await self.vector_client.delete(cube_id)
        if self.timeline_writer:
            await self.timeline_writer.write(
                event_type="evicted",
                cube_id=cube_id,
            )

    async def list_recent(self, session_id: str, limit: int = 20) -> list[MemCube]:
        """Return most recent N episodic memories for a session, newest first."""
        from memora.storage.mongo.collections import MEM_CUBES
        from memora.storage.vector.mongo_vector_client import _doc_to_cube
        cursor = self.vector_client.collection.find(
            {
                "memory_type": "episodic",
                "provenance.session_id": session_id,
            },
            sort=[("provenance.created_at", -1)],
            limit=limit,
        )
        cubes = []
        async for doc in cursor:
            cubes.append(_doc_to_cube(doc))
        return cubes

    async def update_access(self, cube_id: str) -> None:
        """Increment access_count and update provenance.updated_at."""
        from datetime import datetime, timezone
        result = await self.vector_client.collection.update_one(
            {"_id": cube_id},
            {
                "$inc": {"access_count": 1},
                "$set": {"provenance.updated_at": datetime.now(timezone.utc).replace(tzinfo=None)},
            }
        )
        if result.matched_count == 0:
            raise MemoryNotFoundError(cube_id)
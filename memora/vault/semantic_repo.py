"""SemanticRepo implements ISemanticRepo.

Stores and retrieves semantic MemCubes with key-based upsert.
"""

from typing import Optional, List
from datetime import datetime, timezone
from memora.core.interfaces import ISemanticRepo
from memora.core.types import MemCube, MemoryType
from memora.core.errors import MemoryNotFoundError, DuplicateMemoryError
from memora.vault.timeline_writer import TimelineWriter
from memora.storage.vector.mongo_vector_client import MongoVectorClient


class SemanticRepo(ISemanticRepo):
    """MongoDB implementation of semantic memory repository."""

    def __init__(self, vector_client: MongoVectorClient, timeline_writer: TimelineWriter):
        self.vector_client = vector_client
        self.timeline_writer = timeline_writer

    async def save(self, cube: MemCube) -> str:
        """Persist a semantic MemCube. Returns the cube.id."""
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

    async def upsert_by_key(self, key: str, cube: MemCube) -> str:
        """
        Upsert semantic fact by key.
        If a document with extra.key == key exists, update it.
        Otherwise insert new document.
        """
        from memora.storage.vector.mongo_vector_client import _cube_to_doc
        doc = _cube_to_doc(cube)
        doc["extra"]["key"] = key

        existing = await self.vector_client.collection.find_one(
            {"extra.key": key, "memory_type": "semantic"}
        )

        if existing:
            # Update existing — preserve created_at
            if existing.get("provenance"):
                doc["provenance"]["created_at"] = existing["provenance"]["created_at"]
            await self.vector_client.collection.replace_one(
                {"_id": existing["_id"]}, doc
            )
            if self.timeline_writer:
                await self.timeline_writer.write(
                    event_type="updated",
                    cube_id=existing["_id"],
                    session_id=cube.provenance.session_id if cube.provenance else None,
                )
            return existing["_id"]
        else:
            await self.vector_client.upsert(cube)
            if self.timeline_writer:
                await self.timeline_writer.write(
                    event_type="created",
                    cube_id=cube.id,
                    session_id=cube.provenance.session_id if cube.provenance else None,
                )
            return cube.id
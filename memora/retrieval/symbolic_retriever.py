"""SymbolicRetriever module.

Performs exact keyword or tag-based matching using document database.
"""

from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from memora.core.types import MemCube, MemoryType


class SymbolicRetriever:
    """Retrieves memories using exact attribute or tag matching."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        from memora.storage.mongo.collections import MEM_CUBES
        self.collection = db[MEM_CUBES]
        
    async def search_by_tags(
        self,
        tags: list[str],
        top_k: int = 10,
    ) -> list[MemCube]:
        """
        Return MemCubes that contain ALL specified tags.
        MongoDB $all operator on the tags array.
        """
        from memora.storage.vector.mongo_vector_client import _doc_to_cube
        if not tags:
            return []
        cursor = self.collection.find(
            {"tags": {"$all": tags}},
            sort=[("access_count", -1), ("provenance.updated_at", -1)],
            limit=top_k,
        )
        results = []
        async for doc in cursor:
            results.append(_doc_to_cube(doc))
        return results
        
    async def search_by_type(
        self,
        memory_type: MemoryType,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[MemCube]:
        """Filter by memory_type, optionally within a session."""
        from memora.storage.vector.mongo_vector_client import _doc_to_cube
        query: dict = {"memory_type": memory_type.value}
        if session_id:
            query["provenance.session_id"] = session_id
        cursor = self.collection.find(
            query,
            sort=[("provenance.created_at", -1)],
            limit=limit,
        )
        results = []
        async for doc in cursor:
            results.append(_doc_to_cube(doc))
        return results

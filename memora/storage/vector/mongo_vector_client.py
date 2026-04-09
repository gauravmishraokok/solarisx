"""
storage/vector/mongo_vector_client.py

MongoDB Atlas Vector Search client.
Implements IVectorSearch using Atlas $vectorSearch aggregation pipeline.

Replaces: storage/postgres/pgvector_client.py

The embedding_index Atlas Vector Search index must exist on mem_cubes.embedding
before similarity_search() will work. See collections.py for setup instructions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from memora.core.errors import (
    EmbeddingDimensionError,
    MemoryNotFoundError,
)
from memora.core.interfaces import IVectorSearch
from memora.core.types import MemCube, MemoryType
from memora.storage.mongo.collections import MEM_CUBES


def _cube_to_doc(cube: MemCube) -> dict:
    """
    Serialize a MemCube to a MongoDB document.
    Uses cube.id as _id for natural document identity.
    """
    doc = {
        "_id": cube.id,
        "content": cube.content,
        "memory_type": cube.memory_type.value,
        "tier": cube.tier.value,
        "tags": cube.tags,
        "embedding": cube.embedding or [],
        "access_count": cube.access_count,
        "ttl_seconds": cube.ttl_seconds,
        "extra": cube.extra or {},
    }
    if cube.provenance:
        doc["provenance"] = {
            "origin": cube.provenance.origin,
            "session_id": cube.provenance.session_id,
            "created_at": cube.provenance.created_at,
            "updated_at": cube.provenance.updated_at,
            "version": cube.provenance.version,
            "parent_id": cube.provenance.parent_id,
        }
    else:
        doc["provenance"] = None
    return doc


def _doc_to_cube(doc: dict) -> MemCube:
    """
    Deserialize a MongoDB document back to a MemCube.
    Reconstructs Provenance and enum fields.
    """
    from memora.core.types import MemoryTier, Provenance

    provenance = None
    if doc.get("provenance"):
        p = doc["provenance"]
        provenance = Provenance(
            origin=p["origin"],
            session_id=p["session_id"],
            created_at=p["created_at"] if isinstance(p["created_at"], datetime)
                       else datetime.fromisoformat(p["created_at"]),
            updated_at=p["updated_at"] if isinstance(p["updated_at"], datetime)
                       else datetime.fromisoformat(p["updated_at"]),
            version=p["version"],
            parent_id=p.get("parent_id"),
        )

    return MemCube(
        id=doc["_id"],
        content=doc["content"],
        memory_type=MemoryType(doc["memory_type"]),
        tier=MemoryTier(doc["tier"]),
        tags=doc.get("tags", []),
        embedding=doc.get("embedding") or None,
        provenance=provenance,
        access_count=doc.get("access_count", 0),
        ttl_seconds=doc.get("ttl_seconds"),
        extra=doc.get("extra", {}),
    )


class MongoVectorClient(IVectorSearch):
    """
    Atlas Vector Search implementation of IVectorSearch.

    Requires:
    - Motor database instance (from get_database())
    - Atlas Vector Search index named "embedding_index" on mem_cubes.embedding
      with numDimensions=384 and similarity=cosine
    """

    def __init__(self, db: AsyncIOMotorDatabase, embedding_dim: int = 384):
        self.db = db
        self.collection = db[MEM_CUBES]
        self.embedding_dim = embedding_dim

    async def upsert(self, cube: MemCube) -> None:
        """
        Insert or update a MemCube document.
        Uses replace_one with upsert=True on _id.

        Raises:
            EmbeddingDimensionError: if embedding is provided but wrong dimension
        """
        if cube.embedding is not None and len(cube.embedding) != self.embedding_dim:
            raise EmbeddingDimensionError(
                expected=self.embedding_dim,
                got=len(cube.embedding)
            )

        doc = _cube_to_doc(cube)
        await self.collection.replace_one(
            {"_id": cube.id},
            doc,
            upsert=True,
        )

    async def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        memory_types: list[MemoryType] | None = None,
    ) -> list[tuple[MemCube, float]]:
        """
        Atlas Vector Search cosine similarity query.

        Uses $vectorSearch aggregation pipeline against the embedding_index.
        numCandidates = top_k * 10 gives good recall vs latency balance.

        Args:
            query_embedding: 384-dim unit-normalized query vector
            top_k: number of results to return
            memory_types: optional filter by MemoryType

        Returns:
            list of (MemCube, score) sorted by score DESC
            score is Atlas vectorSearchScore (cosine similarity proxy, higher = more similar)
        """
        vector_search_stage = {
            "$vectorSearch": {
                "index": "embedding_index",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": top_k * 10,
                "limit": top_k * 2,  # fetch extra, filter in next stage
            }
        }

        pipeline = [vector_search_stage]

        # Optional memory_type filter after vector search
        if memory_types:
            pipeline.append({
                "$match": {
                    "memory_type": {"$in": [mt.value for mt in memory_types]}
                }
            })

        # Add the vector search score as a field
        pipeline.append({
            "$addFields": {
                "search_score": {"$meta": "vectorSearchScore"}
            }
        })

        # Limit to top_k after filtering
        pipeline.append({"$limit": top_k})

        cursor = self.collection.aggregate(pipeline)
        results = []
        async for doc in cursor:
            score = doc.pop("search_score", 0.0)
            cube = _doc_to_cube(doc)
            results.append((cube, float(score)))

        return results

    async def delete(self, cube_id: str) -> None:
        """
        Hard delete a document by ID.

        Raises:
            MemoryNotFoundError: if cube_id does not exist
        """
        result = await self.collection.delete_one({"_id": cube_id})
        if result.deleted_count == 0:
            raise MemoryNotFoundError(cube_id)

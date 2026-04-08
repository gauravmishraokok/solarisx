"""PgVectorClient implements IVectorSearch.

Provides similarity search over mem_cubes embedding column.
"""

from typing import List, Tuple, Optional
import asyncio
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from memora.core.interfaces import IVectorSearch
from memora.core.types import MemCube, MemoryType
from memora.core.errors import StorageConnectionError


class PgVectorClient(IVectorSearch):
    """Concrete vector search using pgvector extension."""
    
    def __init__(self, session_factory):
        self.session_factory = session_factory
    
    async def similarity_search(self, query_embedding: List[float],
                                top_k: int = 5,
                                memory_types: Optional[List[MemoryType]] = None) -> List[Tuple[MemCube, float]]:
        """
        Return top_k MemCubes most similar to query_embedding.
        Each result is (MemCube, cosine_similarity_score).
        Optional filter by memory_types.
        """
        if not query_embedding:
            return []
        
        async with self.session_factory() as session:
            try:
                # Build base query
                query_sql = """
                SELECT id, content, memory_type, tier, tags, embedding, provenance, 
                       access_count, ttl_seconds, extra, created_at, updated_at,
                       1 - (embedding <=> :query_vector) as similarity
                FROM mem_cubes 
                WHERE embedding IS NOT NULL
                """
                params = {"query_vector": query_embedding}
                
                # Add memory type filter if specified
                if memory_types:
                    type_values = [t.value for t in memory_types]
                    query_sql += " AND memory_type = ANY(:memory_types)"
                    params["memory_types"] = type_values
                
                # Order by similarity and limit
                query_sql += " ORDER BY similarity DESC LIMIT :limit"
                params["limit"] = top_k
                
                result = await session.execute(text(query_sql), params)
                rows = result.fetchall()
                
                # Convert to MemCube objects
                cubes = []
                for row in rows:
                    cube_data = {
                        "id": str(row.id),
                        "content": row.content,
                        "memory_type": row.memory_type,
                        "tier": row.tier,
                        "tags": row.tags or [],
                        "embedding": row.embedding,
                        "provenance": row.provenance,
                        "access_count": row.access_count,
                        "ttl_seconds": row.ttl_seconds,
                        "extra": row.extra or {}
                    }
                    cube = MemCube.from_dict(cube_data)
                    similarity = float(row.similarity)
                    cubes.append((cube, similarity))
                
                return cubes
                
            except Exception as e:
                raise StorageConnectionError(f"Vector search failed: {e}")
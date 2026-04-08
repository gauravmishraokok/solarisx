"""
vault/mem_cube.py - MemCube factory + serialization helpers.

Responsibilities:
- Create MemCube instances with proper provenance
- Serialize/deserialize to/from DB row format
- Validate content before storage

Does NOT: write to DB (that's episodic_repo / semantic_repo / kg_repo)
Does NOT: decide which tier (that's tier_router)
"""
from memora.core.types import MemCube, MemoryType, MemoryTier, Provenance
from memora.core.interfaces import IEmbeddingModel
from typing import Optional
import uuid
from datetime import datetime, timezone


class MemCubeFactory:
    """Factory for creating MemCube instances with proper validation and provenance."""
    
    def __init__(self, embedding_model: IEmbeddingModel):
        self.embedder = embedding_model

    async def create(
        self,
        content: str,
        memory_type: MemoryType,
        session_id: str,
        origin: str = "agent_inference",
        tags: Optional[list[str]] = None,
        extra: Optional[dict] = None,
    ) -> MemCube:
        """Create a new MemCube with embedding and provenance."""
        # Validate content
        if not content.strip():
            raise ValueError("Content cannot be empty")
        
        # Generate embedding
        embedding = await self.embedder.embed(content)
        
        # Create provenance
        provenance = Provenance.new(origin=origin, session_id=session_id)
        
        # Create MemCube
        cube = MemCube(
            id=str(uuid.uuid4()),
            content=content,
            memory_type=memory_type,
            tier=MemoryTier.WARM,  # Default tier, router will decide final tier
            tags=tags or [],
            embedding=embedding,
            provenance=provenance,
            access_count=0,
            ttl_seconds=None,
            extra=extra or {}
        )
        
        return cube

    def to_db_row(self, cube: MemCube) -> dict:
        """Serialize MemCube to flat dict for PostgreSQL storage."""
        return {
            "id": cube.id,
            "content": cube.content,
            "memory_type": cube.memory_type.value,
            "tier": cube.tier.value,
            "tags": cube.tags,
            "embedding": cube.embedding,
            "provenance": {
                "origin": cube.provenance.origin,
                "session_id": cube.provenance.session_id,
                "created_at": cube.provenance.created_at.isoformat(),
                "updated_at": cube.provenance.updated_at.isoformat(),
                "version": cube.provenance.version,
                "parent_id": cube.provenance.parent_id
            } if cube.provenance else None,
            "access_count": cube.access_count,
            "ttl_seconds": cube.ttl_seconds,
            "extra": cube.extra,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None)
        }

    def from_db_row(self, row: dict) -> MemCube:
        """Deserialize from PostgreSQL row to MemCube."""
        # Parse provenance if present
        provenance = None
        if row.get("provenance"):
            prov_data = row["provenance"]
            provenance = Provenance(
                origin=prov_data["origin"],
                session_id=prov_data["session_id"],
                created_at=datetime.fromisoformat(prov_data["created_at"]),
                updated_at=datetime.fromisoformat(prov_data["updated_at"]),
                version=prov_data["version"],
                parent_id=prov_data.get("parent_id")
            )
        
        return MemCube(
            id=row["id"],
            content=row["content"],
            memory_type=MemoryType(row["memory_type"]),
            tier=MemoryTier(row["tier"]),
            tags=row["tags"] or [],
            embedding=row["embedding"],
            provenance=provenance,
            access_count=row["access_count"],
            ttl_seconds=row.get("ttl_seconds"),
            extra=row.get("extra", {})
        )

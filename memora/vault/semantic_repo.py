"""SemanticRepo implements ISemanticRepo.

Stores and retrieves semantic MemCubes with key-based upsert.
"""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from datetime import datetime, timezone
from memora.core.interfaces import ISemanticRepo
from memora.core.types import MemCube, MemoryType
from memora.core.errors import MemoryNotFoundError, DuplicateMemoryError
from memora.storage.postgres.models import MemCubeORM
from memora.vault.timeline_writer import TimelineWriter


class SemanticRepo(ISemanticRepo):
    """PostgreSQL implementation of semantic memory repository."""
    
    def __init__(self, session_factory, timeline_writer: TimelineWriter | None = None):
        self.session_factory = session_factory
        self.timeline = timeline_writer
    
    async def save(self, cube: MemCube) -> str:
        """Persist a semantic MemCube. Returns the cube.id."""
        async with self.session_factory() as session:
            try:
                # Check for duplicate
                existing = await session.get(MemCubeORM, cube.id)
                if existing:
                    raise DuplicateMemoryError(cube.id)
                
                # Convert to ORM model
                orm_cube = MemCubeORM(
                    id=cube.id,
                    content=cube.content,
                    memory_type=cube.memory_type.value,
                    tier=cube.tier.value,
                    tags=cube.tags,
                    embedding=cube.embedding,
                    provenance={
                        "origin": cube.provenance.origin,
                        "session_id": cube.provenance.session_id,
                        "created_at": cube.provenance.created_at,
                        "updated_at": cube.provenance.updated_at,
                        "version": cube.provenance.version,
                        "parent_id": cube.provenance.parent_id
                    } if cube.provenance else None,
                    access_count=cube.access_count,
                    ttl_seconds=cube.ttl_seconds,
                    extra=cube.extra
                )
                
                session.add(orm_cube)
                await session.commit()
                await session.refresh(orm_cube)

                if self.timeline:
                    await self.timeline.write(
                        event_type="created",
                        cube_id=cube.id,
                        session_id=cube.provenance.session_id if cube.provenance else None,
                        description=f"Semantic memory saved: {cube.content[:80]}",
                    )
                return cube.id
                
            except Exception as e:
                await session.rollback()
                raise e
    
    async def get(self, cube_id: str) -> Optional[MemCube]:
        """Fetch by ID. Returns None if not found."""
        async with self.session_factory() as session:
            orm_cube = await session.get(MemCubeORM, cube_id)
            if not orm_cube:
                return None
            
            return self._orm_to_memcube(orm_cube)
    
    async def delete(self, cube_id: str) -> None:
        """Hard delete. Raises MemoryNotFoundError if not found."""
        async with self.session_factory() as session:
            orm_cube = await session.get(MemCubeORM, cube_id)
            if not orm_cube:
                raise MemoryNotFoundError(cube_id)
            
            await session.delete(orm_cube)
            await session.commit()
            if self.timeline:
                await self.timeline.write(
                    event_type="evicted",
                    cube_id=cube_id,
                    description="Semantic memory hard-deleted",
                )
    
    async def upsert_by_key(self, key: str, cube: MemCube) -> str:
        """Upsert: if a semantic memory with this key exists, update it. Otherwise insert."""
        async with self.session_factory() as session:
            try:
                # Look for existing semantic memory with matching content (using key as content identifier)
                # For semantic memories, we use the first tag as the key
                existing_query = select(MemCubeORM).where(
                    MemCubeORM.memory_type == MemoryType.SEMANTIC.value,
                    MemCubeORM.tags.any(key)  # Check if key is in tags array
                )
                result = await session.execute(existing_query)
                existing_orm = result.scalar_one_or_none()
                
                if existing_orm:
                    # Update existing record
                    existing_orm.content = cube.content
                    existing_orm.embedding = cube.embedding
                    existing_orm.tier = cube.tier.value
                    existing_orm.tags = cube.tags
                    existing_orm.extra = cube.extra
                    existing_orm.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    
                    if cube.provenance:
                        existing_orm.provenance = {
                            "origin": cube.provenance.origin,
                            "session_id": cube.provenance.session_id,
                            "created_at": cube.provenance.created_at,
                            "updated_at": cube.provenance.updated_at,
                            "version": cube.provenance.version,
                            "parent_id": cube.provenance.parent_id
                        }
                    
                    await session.commit()
                    if self.timeline:
                        await self.timeline.write(
                            event_type="updated",
                            cube_id=str(existing_orm.id),
                            description=f"Semantic memory upserted (key={key}): {cube.content[:80]}",
                        )
                    return str(existing_orm.id)
                else:
                    # Insert new record with key in tags
                    cube.tags = [key] + (cube.tags or [])
                    orm_cube = MemCubeORM(
                        id=cube.id,
                        content=cube.content,
                        memory_type=cube.memory_type.value,
                        tier=cube.tier.value,
                        tags=cube.tags,
                        embedding=cube.embedding,
                        provenance={
                            "origin": cube.provenance.origin,
                            "session_id": cube.provenance.session_id,
                            "created_at": cube.provenance.created_at,
                            "updated_at": cube.provenance.updated_at,
                            "version": cube.provenance.version,
                            "parent_id": cube.provenance.parent_id
                        } if cube.provenance else None,
                        access_count=cube.access_count,
                        ttl_seconds=cube.ttl_seconds,
                        extra=cube.extra
                    )
                    
                    session.add(orm_cube)
                    await session.commit()
                    await session.refresh(orm_cube)

                    if self.timeline:
                        await self.timeline.write(
                            event_type="created",
                            cube_id=cube.id,
                            description=f"Semantic memory inserted (key={key}): {cube.content[:80]}",
                        )
                    return cube.id
                    
            except Exception as e:
                await session.rollback()
                raise e
    
    def _orm_to_memcube(self, orm_cube: MemCubeORM) -> MemCube:
        """Convert ORM model to MemCube domain object."""
        # Parse provenance if present
        provenance = None
        if orm_cube.provenance:
            prov_data = orm_cube.provenance
            from memora.core.types import Provenance
            from datetime import datetime, timezone
            provenance = Provenance(
                origin=prov_data["origin"],
                session_id=prov_data["session_id"],
                created_at=datetime.fromisoformat(prov_data["created_at"]) if isinstance(prov_data["created_at"], str) else prov_data["created_at"],
                updated_at=datetime.fromisoformat(prov_data["updated_at"]) if isinstance(prov_data["updated_at"], str) else prov_data["updated_at"],
                version=prov_data["version"],
                parent_id=prov_data.get("parent_id")
            )
        
        return MemCube(
            id=str(orm_cube.id),
            content=orm_cube.content,
            memory_type=MemoryType(orm_cube.memory_type),
            tier=MemoryType(orm_cube.tier),
            tags=orm_cube.tags or [],
            embedding=orm_cube.embedding,
            provenance=provenance,
            access_count=orm_cube.access_count,
            ttl_seconds=orm_cube.ttl_seconds,
            extra=orm_cube.extra or {}
        )
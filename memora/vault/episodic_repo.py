"""EpisodicRepo implements IEpisodicRepo.

Stores and retrieves episodic MemCubes with session-based queries.
"""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from memora.core.interfaces import IEpisodicRepo
from memora.core.types import MemCube, MemoryType
from memora.core.errors import MemoryNotFoundError, DuplicateMemoryError
from memora.storage.postgres.models import MemCubeORM, EpisodeORM
from memora.storage.postgres.connection import get_async_session
from memora.storage.postgres.models import Base
from memora.vault.timeline_writer import TimelineWriter


class EpisodicRepo(IEpisodicRepo):
    """PostgreSQL implementation of episodic memory repository."""
    
    def __init__(self, session_factory, timeline_writer: TimelineWriter | None = None):
        self.session_factory = session_factory
        self.timeline = timeline_writer
    
    async def save(self, cube: MemCube) -> str:
        """Persist an episodic MemCube. Returns the cube.id."""
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
                        description=f"Episodic memory saved: {cube.content[:80]}",
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
                    description="Episodic memory hard-deleted",
                )
    
    async def list_recent(self, session_id: str, limit: int = 20) -> List[MemCube]:
        """Return most recent N episodic memories for a session, newest first."""
        async with self.session_factory() as session:
            # Query MemCubes with episodic type and matching session_id in provenance
            query = select(MemCubeORM).where(
                MemCubeORM.memory_type == MemoryType.EPISODIC.value,
                MemCubeORM.provenance["session_id"].as_string() == session_id
            ).order_by(MemCubeORM.created_at.desc()).limit(limit)
            
            result = await session.execute(query)
            orm_cubes = result.scalars().all()
            
            return [self._orm_to_memcube(orm_cube) for orm_cube in orm_cubes]
    
    async def update_access(self, cube_id: str) -> None:
        """Increment access_count and update provenance.updated_at."""
        async with self.session_factory() as session:
            orm_cube = await session.get(MemCubeORM, cube_id)
            if not orm_cube:
                raise MemoryNotFoundError(cube_id)
            
            # Increment access count
            orm_cube.access_count += 1
            
            # Update provenance timestamp if exists
            if orm_cube.provenance:
                from datetime import datetime, timezone
                orm_cube.provenance["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)

            await session.commit()
            if self.timeline:
                await self.timeline.write(
                    event_type="updated",
                    cube_id=cube_id,
                    description="access_count incremented",
                )
            return
            
            # commit already done above if provenance existed
    
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
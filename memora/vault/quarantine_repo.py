"""QuarantineRepo implements IQuarantineRepo.

Manages quarantine records for contradictory memories.
"""

from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from uuid import uuid4
from datetime import datetime, timezone
from memora.core.interfaces import IQuarantineRepo
from memora.core.types import MemCube, ContradictionVerdict, QuarantineStatus
from memora.core.errors import MemoryNotFoundError
from memora.storage.postgres.models import MemCubeORM, ContradictionORM, QuarantineLogORM


class QuarantineRepo(IQuarantineRepo):
    """PostgreSQL implementation of quarantine repository."""
    
    def __init__(self, session_factory):
        self.session_factory = session_factory
    
    async def save_pending(self, cube: MemCube, verdict: ContradictionVerdict) -> str:
        """Create a new quarantine record. Returns quarantine_id."""
        async with self.session_factory() as session:
            try:
                # Create contradiction record
                contradiction = ContradictionORM(
                    id=str(uuid4()),
                    incoming_cube_id=cube.id,
                    conflicting_cube_id=verdict.conflicting_id,
                    score=verdict.score,
                    reasoning=verdict.reasoning,
                    is_quarantined=verdict.is_quarantined,
                    suggested_resolution=verdict.suggested_resolution
                )
                session.add(contradiction)
                
                # Create quarantine log
                quarantine_id = f"quarantine-{cube.id[:8]}-{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d%H%M%S')}"
                quarantine_log = QuarantineLogORM(
                    id=str(uuid4()),
                    quarantine_id=quarantine_id,
                    cube_id=cube.id,
                    contradiction_id=contradiction.id,
                    status=QuarantineStatus.PENDING.value
                )
                session.add(quarantine_log)
                
                await session.commit()
                return quarantine_id
                
            except Exception as e:
                await session.rollback()
                raise e
    
    async def list_pending(self) -> List[Dict]:
        """Return all pending quarantines with cube and verdict details."""
        async with self.session_factory() as session:
            query = select(QuarantineLogORM, ContradictionORM, MemCubeORM).join(
                ContradictionORM, QuarantineLogORM.contradiction_id == ContradictionORM.id
            ).join(
                MemCubeORM, QuarantineLogORM.cube_id == MemCubeORM.id
            ).where(
                QuarantineLogORM.status == QuarantineStatus.PENDING.value
            )
            
            result = await session.execute(query)
            records = result.all()
            
            quarantines = []
            for quarantine_log, contradiction, cube in records:
                quarantines.append({
                    "quarantine_id": quarantine_log.quarantine_id,
                    "cube": self._orm_to_memcube(cube),
                    "verdict": ContradictionVerdict(
                        incoming_id=contradiction.incoming_cube_id,
                        conflicting_id=contradiction.conflicting_cube_id,
                        score=contradiction.score,
                        reasoning=contradiction.reasoning,
                        is_quarantined=contradiction.is_quarantined,
                        suggested_resolution=contradiction.suggested_resolution
                    ),
                    "created_at": quarantine_log.created_at
                })
            
            return quarantines
    
    async def get(self, quarantine_id: str) -> Optional[Dict]:
        """Get full quarantine details by ID."""
        async with self.session_factory() as session:
            query = select(QuarantineLogORM, ContradictionORM, MemCubeORM).join(
                ContradictionORM, QuarantineLogORM.contradiction_id == ContradictionORM.id
            ).join(
                MemCubeORM, QuarantineLogORM.cube_id == MemCubeORM.id
            ).where(
                QuarantineLogORM.quarantine_id == quarantine_id
            )
            
            result = await session.execute(query)
            record = result.first()
            
            if not record:
                return None
            
            quarantine_log, contradiction, cube = record
            return {
                "quarantine_id": quarantine_log.quarantine_id,
                "cube": self._orm_to_memcube(cube),
                "verdict": ContradictionVerdict(
                    incoming_id=contradiction.incoming_cube_id,
                    conflicting_id=contradiction.conflicting_cube_id,
                    score=contradiction.score,
                    reasoning=contradiction.reasoning,
                    is_quarantined=contradiction.is_quarantined,
                    suggested_resolution=contradiction.suggested_resolution
                ),
                "status": QuarantineStatus(quarantine_log.status),
                "merged_content": quarantine_log.merged_content,
                "created_at": quarantine_log.created_at,
                "resolved_at": quarantine_log.resolved_at
            }
    
    async def resolve(self, quarantine_id: str, status: QuarantineStatus,
                     merged_content: str = "") -> None:
        """Resolve a quarantine with final status and optional merged content."""
        async with self.session_factory() as session:
            try:
                # Update quarantine log
                query = update(QuarantineLogORM).where(
                    QuarantineLogORM.quarantine_id == quarantine_id
                ).values(
                    status=status.value,
                    merged_content=merged_content if status == QuarantineStatus.RESOLVED_MERGE else None,
                    resolved_at=datetime.now(timezone.utc).replace(tzinfo=None)
                )
                
                result = await session.execute(query)
                if result.rowcount == 0:
                    raise MemoryNotFoundError(f"Quarantine {quarantine_id} not found")
                
                await session.commit()
                
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
            memory_type=orm_cube.memory_type,
            tier=orm_cube.tier,
            tags=orm_cube.tags or [],
            embedding=orm_cube.embedding,
            provenance=provenance,
            access_count=orm_cube.access_count,
            ttl_seconds=orm_cube.ttl_seconds,
            extra=orm_cube.extra or {}
        )
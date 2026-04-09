"""QuarantineRepo implements IQuarantineRepo.

Manages quarantine records for contradictory memories.
"""

from typing import Optional, List, Dict
import uuid
from datetime import datetime, timezone
from memora.core.interfaces import IQuarantineRepo
from memora.core.types import MemCube, ContradictionVerdict, QuarantineStatus
from memora.core.errors import MemoryNotFoundError, QuarantineNotFoundError, AlreadyResolvedError
from motor.motor_asyncio import AsyncIOMotorDatabase


class QuarantineRepo(IQuarantineRepo):
    """MongoDB implementation of quarantine repository."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db["quarantine_records"]

    async def save_pending(self, cube: MemCube, verdict: ContradictionVerdict) -> str:
        """Store a quarantined memory. Returns quarantine_id."""
        from datetime import datetime, timezone
        from memora.storage.vector.mongo_vector_client import _cube_to_doc
        quarantine_id = str(uuid.uuid4())
        doc = {
            "_id": quarantine_id,
            "incoming_cube_id": cube.id,
            "conflicting_id": verdict.conflicting_id,
            "contradiction_score": verdict.score,
            "reasoning": verdict.reasoning,
            "suggested_resolution": verdict.suggested_resolution,
            "status": QuarantineStatus.PENDING.value,
            "merged_content": "",
            "incoming_cube_doc": _cube_to_doc(cube),
            "session_id": cube.provenance.session_id if cube.provenance else "",
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "resolved_at": None,
        }
        await self.collection.insert_one(doc)
        return quarantine_id

    async def list_pending(self) -> list[dict]:
        """Return all PENDING quarantine records."""
        cursor = self.collection.find(
            {"status": QuarantineStatus.PENDING.value},
            sort=[("created_at", -1)]
        )
        return await cursor.to_list(None)

    async def get(self, quarantine_id: str) -> Optional[dict]:
        """Fetch a specific quarantine record. Returns None if not found."""
        return await self.collection.find_one({"_id": quarantine_id})

    async def resolve(
        self,
        quarantine_id: str,
        status: QuarantineStatus,
        merged_content: str = "",
    ) -> None:
        """Mark quarantine record as resolved."""
        from datetime import datetime, timezone
        from memora.core.errors import QuarantineNotFoundError, AlreadyResolvedError

        doc = await self.collection.find_one({"_id": quarantine_id})
        if not doc:
            raise QuarantineNotFoundError(quarantine_id)
        if doc["status"] != QuarantineStatus.PENDING.value:
            raise AlreadyResolvedError(f"Already resolved: {quarantine_id}")

        await self.collection.update_one(
            {"_id": quarantine_id},
            {
                "$set": {
                    "status": status.value,
                    "merged_content": merged_content,
                    "resolved_at": datetime.now(timezone.utc).replace(tzinfo=None),
                }
            }
        )
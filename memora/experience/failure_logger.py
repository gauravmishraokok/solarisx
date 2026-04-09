"""FailureLogger module.

Records negative outcomes for the ExperienceLearner to learn from.
"""

from typing import Optional, List
from memora.core.events import EventBus, NegativeOutcomeRecorded
from motor.motor_asyncio import AsyncIOMotorDatabase


class FailureLogger:
    """MongoDB implementation of the failure logger."""
    
    def __init__(self, db: AsyncIOMotorDatabase, bus: EventBus):
        self.collection = db["failure_log"]
        bus.subscribe(NegativeOutcomeRecorded, self.handle)
        
    async def handle(self, event: NegativeOutcomeRecorded) -> None:
        """Handle negative outcome event from the bus."""
        await self.log(
            action=event.action,
            memory_ids=event.memory_ids,
            feedback=event.feedback,
            session_id=event.session_id,
        )
    
    async def log(
        self,
        action: str,
        memory_ids: list[str],
        feedback: str,
        session_id: str,
    ) -> str:
        """Record a failure outcome. Returns failure_log_id."""
        import uuid
        from datetime import datetime, timezone
        entry_id = str(uuid.uuid4())
        await self.collection.insert_one({
            "_id": entry_id,
            "session_id": session_id,
            "action_description": action,
            "memory_cluster_ids": memory_ids,
            "feedback": feedback,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        })
        return entry_id
    
    async def get_patterns(self) -> list[dict]:
        """
        Aggregate failure counts per cube_id across all failure log entries.
        Uses MongoDB $unwind + $group aggregation pipeline.
        Returns list of {cube_id, failure_count, last_failure_at} sorted by count DESC.
        """
        pipeline = [
            {"$unwind": "$memory_cluster_ids"},
            {
                "$group": {
                    "_id": "$memory_cluster_ids",
                    "failure_count": {"$sum": 1},
                    "last_failure_at": {"$max": "$created_at"},
                }
            },
            {"$match": {"failure_count": {"$gte": 1}}},
            {"$sort": {"failure_count": -1}},
            {
                "$project": {
                    "cube_id": "$_id",
                    "failure_count": 1,
                    "last_failure_at": 1,
                    "_id": 0,
                }
            },
        ]
        cursor = self.collection.aggregate(pipeline)
        return await cursor.to_list(None)

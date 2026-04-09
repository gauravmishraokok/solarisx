"""
vault/timeline_writer.py

Writes timeline events to MongoDB timeline_events collection.
Called by repos on every create/update/delete/quarantine/resolve operation.
Silently swallows errors — timeline failure never blocks main operations.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from memora.storage.mongo.collections import TIMELINE_EVENTS


class TimelineWriter:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db[TIMELINE_EVENTS]

    async def write(
        self,
        event_type: str,
        cube_id: Optional[str] = None,
        session_id: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Insert a timeline event document.
        event_type: "created" | "updated" | "quarantined" | "resolved" | "evicted"
        Silently swallows all errors — timeline never blocks repo operations.
        """
        try:
            await self.collection.insert_one({
                "_id": str(uuid.uuid4()),
                "cube_id": cube_id,
                "event_type": event_type,
                "description": description,
                "session_id": session_id,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            })
        except Exception as e:
            print(f"[TimelineWriter] write failed (non-fatal): {e}")

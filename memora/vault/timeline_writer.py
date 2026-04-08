"""
vault/timeline_writer.py

Writes timeline events to the timeline_events table.
Called by repos on every create/update/delete/quarantine/resolve operation.
"""
from datetime import datetime, timezone
from typing import Callable
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class TimelineWriter:
    def __init__(self, session_factory: Callable[[], AsyncSession]):
        self.session_factory = session_factory

    async def write(
        self,
        event_type: str,
        cube_id: str | None = None,
        session_id: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """
        Insert a row into timeline_events.
        event_type: "created" | "updated" | "quarantined" | "resolved" | "evicted"
        Silently swallows errors — timeline failure must never block main operations.
        """
        try:
            async with self.session_factory() as session:
                await session.execute(
                    text("""
                    INSERT INTO timeline_events
                        (id, cube_id, event_type, description, session_id, metadata, created_at)
                    VALUES
                        (:id, :cube_id, :event_type, :description,
                         :session_id, :metadata::jsonb, NOW())
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "cube_id": cube_id,
                        "event_type": event_type,
                        "description": description,
                        "session_id": session_id,
                        "metadata": str(metadata or {}),
                    }
                )
                await session.commit()
        except Exception as e:
            print(f"[TimelineWriter] write failed (non-fatal): {e}")

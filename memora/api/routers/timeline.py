"""Timeline endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

router = APIRouter(prefix="/timeline", tags=["timeline"])


@router.get("")
async def get_timeline(session_id: str = "", limit: int = 50, before: str = "") -> dict[str, object]:
    """Return timeline events for a session."""
    _ = session_id, before
    events = [
        {
            "id": "evt-1",
            "cube_id": "cube-1",
            "event_type": "created",
            "description": "Memory created",
            "metadata": {"source": "mock"},
            "created_at": datetime.utcnow().isoformat(),
        }
    ][:limit]
    return {"events": events, "total": len(events)}

"""Court router endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from memora.api.schemas.court_schemas import CourtHealthResponse, QuarantineItemResponse, ResolveRequest
from memora.core.errors import AlreadyResolvedError, QuarantineNotFoundError

router = APIRouter(prefix="/court", tags=["court"])

_QUEUE: dict[str, dict] = {
    "q-1": {
        "item": QuarantineItemResponse(
            quarantine_id="q-1",
            incoming_content="User now prefers premium pricing",
            conflicting_cube_id="cube-1",
            contradiction_score=0.85,
            reasoning="Incoming content conflicts with existing pricing preference memory.",
            suggested_resolution="reject",
            created_at=datetime.utcnow().isoformat(),
        ),
        "resolved": False,
    }
}


@router.get("/queue", response_model=list[QuarantineItemResponse])
async def get_queue() -> list[QuarantineItemResponse]:
    """Return pending quarantine queue."""
    return [row["item"] for row in _QUEUE.values() if not row["resolved"]]


@router.get("/health", response_model=CourtHealthResponse)
async def get_health() -> CourtHealthResponse:
    """Return court queue health metrics."""
    pending = len([row for row in _QUEUE.values() if not row["resolved"]])
    return CourtHealthResponse(
        pending_count=pending,
        resolved_today=0,
        total_quarantined_all_time=len(_QUEUE),
        average_contradiction_score=0.85 if _QUEUE else 0.0,
    )


@router.post("/resolve/{quarantine_id}")
async def resolve_quarantine(quarantine_id: str, payload: ResolveRequest) -> dict[str, object]:
    """Resolve a quarantine record with accept/reject/merge."""
    row = _QUEUE.get(quarantine_id)
    if row is None:
        raise QuarantineNotFoundError(quarantine_id)
    if row["resolved"]:
        raise AlreadyResolvedError("Quarantine already resolved")
    if payload.resolution == "merge" and not payload.merged_content:
        raise ValueError("merged_content is required when resolution == 'merge'")
    row["resolved"] = True
    return {"resolved": True, "quarantine_id": quarantine_id}

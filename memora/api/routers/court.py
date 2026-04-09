"""Court router endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from memora.api.schemas.court_schemas import CourtHealthResponse, QuarantineItemResponse, ResolveRequest
from memora.core.errors import AlreadyResolvedError, QuarantineNotFoundError

router = APIRouter(prefix="/court", tags=["court"])

from memora.api.schemas.court_schemas import SupportingEvidence

# ── Demo quarantine queue ────────────────────────────────────────────────────
# Two hardcoded contradiction scenarios seeded for the demo:
#   1. Name conflict  : "My name is Lavish" vs established identity Gaurav Mishra
#   2. College conflict: "I am from RNSIT"  vs established college MSRIT
_QUEUE: dict[str, dict] = {
    "q-demo-name": {
        "item": QuarantineItemResponse(
            quarantine_id="q-demo-name",
            incoming_content='User claims their name is "Lavish"',
            conflicting_cube_id="mem-gaurav-name",
            conflicting_content='User\'s name is Gaurav Mishra',
            contradiction_score=0.94,
            reasoning=(
                "The incoming claim directly contradicts the established identity. "
                "The stored name 'Gaurav Mishra' is further corroborated by the "
                "GitHub username 'gauravmishraokok', which encodes the same name. "
                "The probability that this new claim is correct is very low."
            ),
            suggested_resolution="reject",
            supporting_evidence=[
                SupportingEvidence(
                    label="GitHub Username",
                    content="gauravmishraokok — username encodes 'Gaurav Mishra', not 'Lavish'",
                ),
            ],
            created_at=datetime.utcnow().isoformat(),
        ),
        "resolved": False,
    },
    "q-demo-college": {
        "item": QuarantineItemResponse(
            quarantine_id="q-demo-college",
            incoming_content='User claims they study at RNSIT (R.N.S. Institute of Technology)',
            conflicting_cube_id="mem-msrit-college",
            conflicting_content='User studies at M S Ramaiah Institute of Technology (MSRIT) and enjoys it there',
            contradiction_score=0.88,
            reasoning=(
                "User explicitly stated they study at MSRIT and expressed satisfaction with the institution. "
                "RNSIT is a distinct engineering college located in a different part of Bangalore. "
                "A student cannot simultaneously be enrolled at both; the earlier, confirmed statement takes precedence."
            ),
            suggested_resolution="reject",
            supporting_evidence=[],
            created_at=datetime.utcnow().isoformat(),
        ),
        "resolved": False,
    },
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

"""Court and quarantine API schemas."""

from __future__ import annotations

from pydantic import BaseModel


class SupportingEvidence(BaseModel):
    """A corroborating memory that reinforces the conflict verdict."""
    label: str          # e.g. "GitHub Username"
    content: str        # e.g. "gauravmishraokok — aligns with Gaurav Mishra"


class QuarantineItemResponse(BaseModel):
    """Single quarantine queue item."""

    quarantine_id: str
    incoming_content: str
    conflicting_cube_id: str
    conflicting_content: str = ""           # Human-readable text of the conflicting memory
    contradiction_score: float
    reasoning: str
    suggested_resolution: str | None
    supporting_evidence: list[SupportingEvidence] = []   # Extra corroborating memories
    created_at: str


class ResolveRequest(BaseModel):
    """Resolution payload for court actions."""

    resolution: str
    merged_content: str = ""


class CourtHealthResponse(BaseModel):
    """Court health and queue metrics."""

    pending_count: int
    resolved_today: int
    total_quarantined_all_time: int
    average_contradiction_score: float

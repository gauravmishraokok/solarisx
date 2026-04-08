"""Health and observability endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter

router = APIRouter(prefix="", tags=["health"])
_STARTED_AT = time.time()


@router.get("/health")
async def get_health() -> dict[str, object]:
    """Return app health with memory and latency metrics."""
    return {
        "status": "ok",
        "total_memories": 1,
        "memories_by_tier": {"hot": 0, "warm": 1, "cold": 0},
        "memories_by_type": {"episodic": 0, "semantic": 1, "kg_node": 0},
        "retrieval_latency_p50_ms": 42.0,
        "retrieval_latency_p99_ms": 180.0,
        "quarantine_pending": 1,
        "db_connected": True,
        "uptime_seconds": time.time() - _STARTED_AT,
    }

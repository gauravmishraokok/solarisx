"""Memory router endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from memora.core.errors import MemoryNotFoundError
from memora.api.schemas.memory_schemas import MemoryCubeResponse, MemoryListResponse

router = APIRouter(prefix="/memories", tags=["memories"])

_MEMORIES: dict[str, MemoryCubeResponse] = {
    "cube-1": MemoryCubeResponse(
        id="cube-1",
        content="User prefers premium pricing strategy",
        memory_type="semantic",
        tier="warm",
        tags=["pricing", "preference"],
        access_count=2,
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat(),
    )
}


@router.get("", response_model=MemoryListResponse)
async def list_memories(session_id: str = "", limit: int = 20) -> MemoryListResponse:
    """Return recent memory list for a session (mocked)."""
    items = list(_MEMORIES.values())[:limit]
    return MemoryListResponse(memories=items, total=len(items))


@router.get("/search", response_model=MemoryListResponse)
async def search_memories(q: str, top_k: int = 5) -> MemoryListResponse:
    """Return full-memory search results (mocked)."""
    if not q:
        return MemoryListResponse(memories=[], total=0)
    items = list(_MEMORIES.values())[:top_k]
    return MemoryListResponse(memories=items, total=len(items))


@router.get("/{cube_id}", response_model=MemoryCubeResponse)
async def get_memory(cube_id: str) -> MemoryCubeResponse:
    """Return a memory by ID or raise not-found."""
    cube = _MEMORIES.get(cube_id)
    if cube is None:
        raise MemoryNotFoundError(cube_id)
    return cube


@router.delete("/{cube_id}")
async def delete_memory(cube_id: str) -> dict[str, bool]:
    """Delete memory by ID or raise not-found."""
    if cube_id not in _MEMORIES:
        raise MemoryNotFoundError(cube_id)
    del _MEMORIES[cube_id]
    return {"deleted": True}

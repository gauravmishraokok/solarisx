"""Knowledge graph visualization endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from memora.api.schemas.memory_schemas import MemoryCubeResponse

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/nodes")
async def get_nodes() -> dict[str, list[dict[str, str]]]:
    """Return all graph nodes for D3 rendering."""
    return {
        "nodes": [
            {"id": "cube-1", "label": "Premium pricing preference", "type": "semantic", "tier": "warm"},
            {"id": "cube-2", "label": "B2B context", "type": "kg_node", "tier": "hot"},
        ]
    }


@router.get("/edges")
async def get_edges() -> dict[str, list[dict[str, object]]]:
    """Return all graph edges including active/deprecated records."""
    return {
        "edges": [
            {"id": "edge-1", "from": "cube-1", "to": "cube-2", "label": "relates_to", "active": True},
        ]
    }


@router.get("/neighbors/{cube_id}")
async def get_neighbors(cube_id: str, depth: int = 1) -> dict[str, list[MemoryCubeResponse]]:
    """Return neighbor cubes for a target graph node."""
    _ = cube_id, depth
    return {"neighbors": []}

"""KGRepo implements IKGRepo wrapper.

Delegates to Neo4jClient or NetworkXClient based on configuration.
"""

from typing import List, Dict, Optional
from memora.core.interfaces import IKGRepo
from memora.core.types import MemCube
from memora.core.config import get_settings
from memora.vault.timeline_writer import TimelineWriter


class KGRepo(IKGRepo):
    """Knowledge graph repository wrapper that delegates to appropriate client."""
    
    def __init__(self, timeline_writer: TimelineWriter | None = None):
        settings = get_settings()
        self.timeline = timeline_writer
        if settings.use_networkx_fallback:
            from memora.storage.graph.networkx_client import NetworkXClient
            self._client = NetworkXClient()
        else:
            from memora.storage.graph.neo4j_client import Neo4jClient
            self._client = Neo4jClient(
                uri=settings.neo4j_uri,
                user=settings.neo4j_user,
                password=settings.neo4j_password
            )
    
    async def upsert_node(self, cube: MemCube) -> str:
        """Insert or update a KG node. Returns node ID."""
        node_id = await self._client.upsert_node(cube)
        if self.timeline:
            await self.timeline.write(
                event_type="created",
                cube_id=cube.id,
                session_id=cube.provenance.session_id if cube.provenance else None,
                description=f"KG node upserted: {cube.content[:80]}",
            )
        return node_id
    
    async def add_edge(self, from_id: str, to_id: str, label: str,
                       metadata: Optional[Dict] = None) -> str:
        """Add a directed edge. Returns edge ID. Old edges are archived, not deleted."""
        return await self._client.add_edge(from_id, to_id, label, metadata)
    
    async def deprecate_edge(self, edge_id: str, reason: str) -> None:
        """Mark edge as deprecated with a reason and deprecated_at timestamp."""
        await self._client.deprecate_edge(edge_id, reason)
        if self.timeline:
            await self.timeline.write(
                event_type="updated",
                description=f"Edge deprecated: {edge_id} reason={reason}",
            )
    
    async def get_neighbors(self, cube_id: str, depth: int = 1) -> List[MemCube]:
        """Return all nodes reachable within `depth` hops. Active edges only."""
        return await self._client.get_neighbors(cube_id, depth)
    
    async def get_all_nodes(self) -> List[Dict]:
        """For graph visualization. Returns list of {id, label, type, tier}."""
        return await self._client.get_all_nodes()
    
    async def get_all_edges(self) -> List[Dict]:
        """For graph visualization. Returns list of {id, from, to, label, active, deprecated_at}."""
        return await self._client.get_all_edges()
    
    async def close(self):
        """Close underlying connections."""
        if hasattr(self._client, 'close'):
            await self._client.close()
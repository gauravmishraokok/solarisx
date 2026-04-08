"""NetworkXClient implements IKGRepo.

In-memory fallback for when Neo4j is unavailable. Stores graph in NetworkX MultiDiGraph.
"""

from typing import List, Dict, Optional
import networkx as nx
from datetime import datetime
from memora.core.interfaces import IKGRepo
from memora.core.types import MemCube


class NetworkXClient(IKGRepo):
    """In-memory knowledge graph repository using NetworkX."""
    
    def __init__(self):
        self.graph = nx.MultiDiGraph()
    
    async def upsert_node(self, cube: MemCube) -> str:
        """Insert or update a KG node. Returns node ID."""
        self.graph.add_node(
            cube.id,
            content=cube.content,
            type=cube.memory_type.value,
            tier=cube.tier.value,
            tags=cube.tags,
            extra=cube.extra,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        return cube.id
    
    async def add_edge(self, from_id: str, to_id: str, label: str,
                       metadata: Optional[Dict] = None) -> str:
        """Add a directed edge. Returns edge ID. Old edges are archived, not deleted."""
        edge_id = f"{from_id}-{to_id}-{label}"
        self.graph.add_edge(
            from_id, to_id,
            key=edge_id,
            id=edge_id,
            label=label,
            metadata=metadata or {},
            active=True,
            created_at=datetime.utcnow()
        )
        return edge_id
    
    async def deprecate_edge(self, edge_id: str, reason: str) -> None:
        """Mark edge as deprecated with a reason and deprecated_at timestamp."""
        for from_id, to_id, key, data in self.graph.edges(data=True, keys=True):
            if data.get('id') == edge_id:
                data['active'] = False
                data['deprecated_reason'] = reason
                data['deprecated_at'] = datetime.utcnow()
                break
    
    async def get_neighbors(self, cube_id: str, depth: int = 1) -> List[MemCube]:
        """Return all nodes reachable within `depth` hops. Active edges only."""
        # Get neighbors within depth using only active edges
        neighbors_nodes = set()
        current_nodes = {cube_id}
        
        for _ in range(depth):
            next_nodes = set()
            for node in current_nodes:
                for successor in self.graph.successors(node):
                    # Check if any active edge exists
                    for _, succ_data in self.graph.get_edge_data(node, successor, {}).items():
                        if succ_data.get('active', True):
                            next_nodes.add(successor)
                            break
            neighbors_nodes.update(next_nodes)
            current_nodes = next_nodes
            if not current_nodes:
                break
        
        # Convert to MemCube objects
        cubes = []
        for node_id in neighbors_nodes:
            node_data = self.graph.nodes[node_id]
            cube_data = {
                "id": node_id,
                "content": node_data.get("content", ""),
                "memory_type": node_data.get("type", "episodic"),
                "tier": node_data.get("tier", "warm"),
                "tags": node_data.get("tags", []),
                "embedding": None,
                "provenance": None,
                "access_count": 0,
                "ttl_seconds": None,
                "extra": node_data.get("extra", {})
            }
            cube = MemCube.from_dict(cube_data)
            cubes.append(cube)
        
        return cubes
    
    async def get_all_nodes(self) -> List[Dict]:
        """For graph visualization. Returns list of {id, label, type, tier}."""
        nodes_data = []
        for node_id, data in self.graph.nodes(data=True):
            nodes_data.append({
                "id": node_id,
                "label": data.get("content", ""),
                "type": data.get("type", "episodic"),
                "tier": data.get("tier", "warm")
            })
        return nodes_data
    
    async def get_all_edges(self) -> List[Dict]:
        """For graph visualization. Returns list of {id, from, to, label, active, deprecated_at}."""
        edges_data = []
        for from_id, to_id, key, data in self.graph.edges(data=True, keys=True):
            edges_data.append({
                "id": data.get("id", f"{from_id}-{to_id}"),
                "from": from_id,
                "to": to_id,
                "label": data.get("label", ""),
                "active": data.get("active", True),
                "deprecated_at": data.get("deprecated_at")
            })
        return edges_data
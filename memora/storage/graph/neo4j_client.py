"""Neo4jClient implements IKGRepo.

Stores KG nodes/edges in Neo4j. Active edges only; deprecation creates new edge with deprecated_at timestamp.
"""

from typing import List, Dict, Optional
from neo4j import AsyncGraphDatabase
from memora.core.interfaces import IKGRepo
from memora.core.types import MemCube
from memora.core.errors import StorageConnectionError


class Neo4jClient(IKGRepo):
    """Concrete knowledge graph repository using Neo4j."""
    
    def __init__(self, uri: str, user: str, password: str):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    
    async def close(self):
        await self.driver.close()
    
    async def upsert_node(self, cube: MemCube) -> str:
        """Insert or update a KG node. Returns node ID."""
        async with self.driver.session() as session:
            try:
                query = """
                MERGE (n:KGNode {id: $id})
                ON CREATE SET 
                    n.id = $id,
                    n.content = $content,
                    n.type = $memory_type,
                    n.tier = $tier,
                    n.tags = $tags,
                    n.extra = $extra,
                    n.created_at = datetime()
                ON MATCH SET
                    n.content = $content,
                    n.type = $memory_type,
                    n.tier = $tier,
                    n.tags = $tags,
                    n.extra = $extra,
                    n.updated_at = datetime()
                RETURN n.id as id
                """
                result = await session.run(
                    query,
                    id=cube.id,
                    content=cube.content,
                    memory_type=cube.memory_type.value,
                    tier=cube.tier.value,
                    tags=cube.tags,
                    extra=cube.extra
                )
                record = await result.single()
                return str(record["id"])
            except Exception as e:
                raise StorageConnectionError(f"Neo4j upsert_node failed: {e}")
    
    async def add_edge(self, from_id: str, to_id: str, label: str,
                       metadata: Optional[Dict] = None) -> str:
        """Add a directed edge. Returns edge ID. Old edges are archived, not deleted."""
        async with self.driver.session() as session:
            try:
                edge_id = f"{from_id}-{to_id}-{label}"
                query = """
                MATCH (from:KGNode {id: $from_id}), (to:KGNode {id: $to_id})
                CREATE (from)-[e:KG_EDGE {
                    id: $edge_id,
                    label: $label,
                    metadata: $metadata,
                    active: true,
                    created_at: datetime()
                }]->(to)
                RETURN e.id as id
                """
                result = await session.run(
                    query,
                    from_id=from_id,
                    to_id=to_id,
                    label=label,
                    metadata=metadata or {},
                    edge_id=edge_id
                )
                record = await result.single()
                return str(record["id"])
            except Exception as e:
                raise StorageConnectionError(f"Neo4j add_edge failed: {e}")
    
    async def deprecate_edge(self, edge_id: str, reason: str) -> None:
        """Mark edge as deprecated with a reason and deprecated_at timestamp."""
        async with self.driver.session() as session:
            try:
                query = """
                MATCH ()-[e:KG_EDGE {id: $edge_id}]->()
                SET e.active = false,
                    e.deprecated_reason = $reason,
                    e.deprecated_at = datetime()
                """
                await session.run(query, edge_id=edge_id, reason=reason)
            except Exception as e:
                raise StorageConnectionError(f"Neo4j deprecate_edge failed: {e}")
    
    async def get_neighbors(self, cube_id: str, depth: int = 1) -> List[MemCube]:
        """Return all nodes reachable within `depth` hops. Active edges only."""
        async with self.driver.session() as session:
            try:
                query = """
                MATCH (start:KGNode {id: $cube_id})-[*1..$depth]->(neighbor:KGNode)
                WHERE ALL(rel IN relationships(path) WHERE rel.active = true)
                RETURN DISTINCT neighbor.id as id,
                       neighbor.content as content,
                       neighbor.type as memory_type,
                       neighbor.tier as tier,
                       neighbor.tags as tags,
                       neighbor.extra as extra
                """
                result = await session.run(query, cube_id=cube_id, depth=depth)
                records = await result.data()
                
                cubes = []
                for record in records:
                    cube_data = {
                        "id": record["id"],
                        "content": record["content"],
                        "memory_type": record["memory_type"],
                        "tier": record["tier"],
                        "tags": record["tags"] or [],
                        "embedding": None,
                        "provenance": None,
                        "access_count": 0,
                        "ttl_seconds": None,
                        "extra": record["extra"] or {}
                    }
                    cube = MemCube.from_dict(cube_data)
                    cubes.append(cube)
                
                return cubes
            except Exception as e:
                raise StorageConnectionError(f"Neo4j get_neighbors failed: {e}")
    
    async def get_all_nodes(self) -> List[Dict]:
        """For graph visualization. Returns list of {id, label, type, tier}."""
        async with self.driver.session() as session:
            try:
                query = """
                MATCH (n:KGNode)
                RETURN n.id as id,
                       n.content as label,
                       n.type as type,
                       n.tier as tier
                """
                result = await session.run(query)
                records = await result.data()
                return records
            except Exception as e:
                raise StorageConnectionError(f"Neo4j get_all_nodes failed: {e}")
    
    async def get_all_edges(self) -> List[Dict]:
        """For graph visualization. Returns list of {id, from, to, label, active, deprecated_at}."""
        async with self.driver.session() as session:
            try:
                query = """
                MATCH (from)-[e:KG_EDGE]->(to)
                RETURN e.id as id,
                       from.id as from,
                       to.id as to,
                       e.label as label,
                       e.active as active,
                       e.deprecated_at as deprecated_at
                """
                result = await session.run(query)
                records = await result.data()
                return records
            except Exception as e:
                raise StorageConnectionError(f"Neo4j get_all_edges failed: {e}")
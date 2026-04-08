"""Pytest fixtures for MEMORA testing.

Provides mock implementations and test data for isolated unit tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import List
import asyncio

from memora.core.types import MemCube, MemoryType, MemoryTier, Provenance, Episode, ContradictionVerdict
from memora.core.interfaces import (
    IEmbeddingModel, IVectorSearch, IFailureLog, ILLM,
    IEpisodicRepo, ISemanticRepo, IKGRepo, IQuarantineRepo
)
from memora.core.events import EventBus, ConversationTurnEvent, MemoryWriteRequested, MemoryApproved
from memora.core.errors import MemoraError


@pytest.fixture
def mock_embedder():
    """Mock IEmbeddingModel returning deterministic 384-dim vectors."""
    embedder = AsyncMock(spec=IEmbeddingModel)
    
    async def embed(text: str) -> List[float]:
        # Return deterministic vector based on text hash
        import hashlib
        hash_obj = hashlib.md5(text.encode())
        seed = int(hash_obj.hexdigest()[:8], 16)
        import random
        random.seed(seed)
        return [random.random() for _ in range(384)]
    
    async def embed_batch(texts: List[str]) -> List[List[float]]:
        return [await embed(text) for text in texts]
    
    embedder.embed.side_effect = embed
    embedder.embed_batch.side_effect = embed_batch
    
    return embedder


@pytest.fixture
def mock_llm():
    """Mock ILLM returning deterministic responses."""
    llm = AsyncMock(spec=ILLM)
    
    async def complete(system: str, user: str, max_tokens: int = 1000) -> str:
        # Return deterministic response based on prompt hash
        import hashlib
        hash_obj = hashlib.md5(f"{system}:{user}".encode())
        seed = int(hash_obj.hexdigest()[:8], 16)
        
        responses = [
            "This is a test response from the mock LLM.",
            "Based on the context, I would suggest...",
            "The memory appears to be consistent.",
            "There seems to be a contradiction here.",
            "I recommend accepting this memory."
        ]
        
        import random
        random.seed(seed)
        return random.choice(responses)
    
    async def complete_json(system: str, user: str, schema: dict, max_tokens: int = 1000) -> dict:
        # Return default JSON response per spec
        return {
            "contradiction_score": 0.10,
            "reasoning": "No contradiction found",
            "suggested_resolution": "accept"
        }
    
    llm.complete.side_effect = complete
    llm.complete_json.side_effect = complete_json
    return llm


@pytest.fixture
def mock_vector_store():
    """Mock IVectorSearch returning deterministic similarity results."""
    vector_store = AsyncMock(spec=IVectorSearch)
    
    async def similarity_search(query_embedding: List[float], top_k: int = 5, memory_types: List[MemoryType] = None):
        # Return deterministic mock results
        cubes = []
        for i in range(min(top_k, 3)):
            cube = MemCube(
                id=f"mock-cube-{i}",
                content=f"Mock content {i}",
                memory_type=MemoryType.EPISODIC,
                tier=MemoryTier.WARM,
                tags=[f"tag{i}"],
                embedding=[0.1 * i] * 384,
                provenance=Provenance.new("test", f"session-{i}")
            )
            similarity = 0.9 - (i * 0.1)
            cubes.append((cube, similarity))
        return cubes
    
    vector_store.similarity_search.side_effect = similarity_search
    return vector_store


@pytest.fixture
def mock_failure_log():
    """Mock IFailureLog for testing failure tracking."""
    failure_log = AsyncMock(spec=IFailureLog)
    
    async def log(action: str, memory_ids: List[str], feedback: str, session_id: str) -> str:
        return f"failure-log-{action}-{session_id}"
    
    async def get_patterns() -> List[dict]:
        return [
            {
                "memory_cluster_ids": ["id1", "id2"],
                "failure_count": 3,
                "last_failure_at": "2024-01-01T00:00:00Z"
            }
        ]
    
    failure_log.log.side_effect = log
    failure_log.get_patterns.side_effect = get_patterns
    
    return failure_log


@pytest.fixture
def cube_factory(mock_embedder):
    """Factory for creating test MemCube instances."""
    async def create_cube(content: str, memory_type: MemoryType = MemoryType.EPISODIC, session_id: str = "test-session") -> MemCube:
        embedding = await mock_embedder.embed(content)
        return MemCube(
            id=f"test-cube-{content[:10]}",
            content=content,
            memory_type=memory_type,
            tier=MemoryTier.WARM,
            tags=["test"],
            embedding=embedding,
            provenance=Provenance.new("test", session_id),
            access_count=0,
            ttl_seconds=None,
            extra={"test": True}
        )
    
    return create_cube


@pytest.fixture
def sample_cubes(cube_factory):
    """Pre-created sample MemCube instances for testing."""
    async def get_cubes():
        cubes = []
        cubes.append(await cube_factory("User asked about weather", MemoryType.EPISODIC, "session-1"))
        cubes.append(await cube_factory("System responded with weather info", MemoryType.EPISODIC, "session-1"))
        cubes.append(await cube_factory("Weather is sunny and 75°F", MemoryType.SEMANTIC, "session-1"))
        cubes.append(await cube_factory("User likes hiking", MemoryType.EPISODIC, "session-2"))
        cubes.append(await cube_factory("Hiking is outdoor activity", MemoryType.SEMANTIC, "session-2"))
        return cubes
    
    return asyncio.run(get_cubes())


@pytest.fixture
def clean_bus():
    """Fresh EventBus instance for each test."""
    bus = EventBus()
    yield bus
    bus.clear()  # Cleanup after test


@pytest.fixture
def mock_episodic_repo():
    """Mock IEpisodicRepo for testing."""
    repo = AsyncMock(spec=IEpisodicRepo)
    
    async def save(cube: MemCube) -> str:
        return cube.id
    
    async def get(cube_id: str):
        return None  # Simulate not found by default
    
    async def delete(cube_id: str):
        pass
    
    async def list_recent(session_id: str, limit: int = 20):
        return []
    
    async def update_access(cube_id: str):
        pass
    
    repo.save.side_effect = save
    repo.get.side_effect = get
    repo.delete.side_effect = delete
    repo.list_recent.side_effect = list_recent
    repo.update_access.side_effect = update_access
    
    return repo


@pytest.fixture
def mock_semantic_repo():
    """Mock ISemanticRepo for testing."""
    repo = AsyncMock(spec=ISemanticRepo)
    
    async def save(cube: MemCube) -> str:
        return cube.id
    
    async def get(cube_id: str):
        return None
    
    async def delete(cube_id: str):
        pass
    
    async def upsert_by_key(key: str, cube: MemCube) -> str:
        return cube.id
    
    repo.save.side_effect = save
    repo.get.side_effect = get
    repo.delete.side_effect = delete
    repo.upsert_by_key.side_effect = upsert_by_key
    
    return repo


@pytest.fixture
def mock_kg_repo():
    """Mock IKGRepo for testing."""
    repo = AsyncMock(spec=IKGRepo)
    
    async def upsert_node(cube: MemCube) -> str:
        return cube.id
    
    async def add_edge(from_id: str, to_id: str, label: str, metadata=None) -> str:
        return f"{from_id}-{to_id}-{label}"
    
    async def deprecate_edge(edge_id: str, reason: str):
        pass
    
    async def get_neighbors(cube_id: str, depth: int = 1):
        return []
    
    async def get_all_nodes():
        return []
    
    async def get_all_edges():
        return []
    
    repo.upsert_node.side_effect = upsert_node
    repo.add_edge.side_effect = add_edge
    repo.deprecate_edge.side_effect = deprecate_edge
    repo.get_neighbors.side_effect = get_neighbors
    repo.get_all_nodes.side_effect = get_all_nodes
    repo.get_all_edges.side_effect = get_all_edges
    
    return repo


@pytest.fixture
def mock_quarantine_repo():
    """Mock IQuarantineRepo for testing."""
    repo = AsyncMock(spec=IQuarantineRepo)
    
    async def save_pending(cube: MemCube, verdict: ContradictionVerdict) -> str:
        return "quarantine-123"
    
    async def list_pending():
        return []
    
    async def get(quarantine_id: str):
        return None
    
    async def resolve(quarantine_id: str, status, merged_content: str = ""):
        pass
    
    repo.save_pending.side_effect = save_pending
    repo.list_pending.side_effect = list_pending
    repo.get.side_effect = get
    repo.resolve.side_effect = resolve
    
    return repo


@pytest.fixture
def sample_episode():
    """Sample Episode instance for testing."""
    return Episode(
        id="episode-123",
        content="User asked about weather and got response",
        start_turn=0,
        end_turn=2,
        session_id="session-1",
        boundary_score=0.8
    )


@pytest.fixture
def sample_contradiction():
    """Sample ContradictionVerdict instance for testing."""
    return ContradictionVerdict(
        incoming_id="cube-123",
        conflicting_id="cube-456",
        score=0.85,
        reasoning="Contradictory weather information",
        is_quarantined=True,
        suggested_resolution="merge: Prefer the more recent weather data"
    )


# Test data fixtures
@pytest.fixture
def sample_conversation_turn():
    """Sample ConversationTurnEvent for testing."""
    return ConversationTurnEvent(
        timestamp=None,  # Will be set automatically
        session_id="test-session",
        user_message="What's the weather like?",
        agent_response="It's sunny and 75°F today.",
        turn_number=0
    )


@pytest.fixture
def sample_memory_write_requested(sample_cubes):
    """Sample MemoryWriteRequested event for testing."""
    return MemoryWriteRequested(
        timestamp=None,
        session_id="test-session",
        cube=sample_cubes[0]
    )


@pytest.fixture
def sample_memory_approved(sample_cubes):
    """Sample MemoryApproved event for testing."""
    return MemoryApproved(
        timestamp=None,
        session_id="test-session",
        cube=sample_cubes[0]
    )
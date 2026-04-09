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
    """
    In-memory vector store mock.
    Now backed by MongoVectorClient interface instead of PgVectorClient.
    Interface is identical — IVectorSearch contract unchanged.
    """
    class InMemoryVectorStore(IVectorSearch):
        def __init__(self):
            self._docs: dict[str, tuple[MemCube, list[float]]] = {}

        async def upsert(self, cube: MemCube) -> None:
            self._docs[cube.id] = (cube, cube.embedding or [])

        async def similarity_search(self, query_embedding, top_k=5, memory_types=None):
            import numpy as np
            results = []
            q = np.array(query_embedding)
            for cube, emb in self._docs.values():
                if memory_types and cube.memory_type not in memory_types:
                    continue
                if not emb:
                    continue
                e = np.array(emb)
                score = float(np.dot(q, e) / (np.linalg.norm(q) * np.linalg.norm(e) + 1e-9))
                results.append((cube, score))
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]

        async def delete(self, cube_id: str) -> None:
            if cube_id not in self._docs:
                from memora.core.errors import MemoryNotFoundError
                raise MemoryNotFoundError(cube_id)
            del self._docs[cube_id]

    return InMemoryVectorStore()


@pytest.fixture
def mock_db():
    """
    In-memory mock of AsyncIOMotorDatabase.
    Returns a simple dict-backed mock for unit tests that need
    quarantine_repo or failure_log without a real Atlas connection.
    """
    class MockCollection:
        def __init__(self):
            self._docs: dict = {}

        async def insert_one(self, doc):
            self._docs[doc["_id"]] = doc

        async def find_one(self, query):
            for doc in self._docs.values():
                if self._matches(doc, query):
                    return dict(doc)
            return None

        async def replace_one(self, query, replacement, upsert=False):
            for key, doc in self._docs.items():
                if self._matches(doc, query):
                    self._docs[key] = replacement
                    return
            if upsert:
                self._docs[replacement["_id"]] = replacement

        async def update_one(self, query, update):
            for doc in self._docs.values():
                if self._matches(doc, query):
                    if "$set" in update:
                        doc.update(update["$set"])
                    if "$inc" in update:
                        for k, v in update["$inc"].items():
                            doc[k] = doc.get(k, 0) + v
                    break

        async def delete_one(self, query):
            class Result:
                deleted_count = 0
            r = Result()
            for key, doc in list(self._docs.items()):
                if self._matches(doc, query):
                    del self._docs[key]
                    r.deleted_count = 1
                    break
            return r

        def find(self, query=None, sort=None, limit=0):
            return MockCursor(list(self._docs.values()), query, sort, limit)

        def aggregate(self, pipeline):
            return MockCursor(list(self._docs.values()))

        def _matches(self, doc, query):
            if not query:
                return True
            for k, v in query.items():
                if doc.get(k) != v:
                    return False
            return True

    class MockCursor:
        def __init__(self, docs, query=None, sort=None, limit=0):
            self._docs = docs
            self._limit = limit

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._docs:
                raise StopAsyncIteration
            return self._docs.pop(0)

        async def to_list(self, n):
            return list(self._docs)

    class MockDB:
        def __init__(self):
            self._collections: dict[str, MockCollection] = {}

        def __getitem__(self, name):
            if name not in self._collections:
                self._collections[name] = MockCollection()
            return self._collections[name]

    return MockDB()


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
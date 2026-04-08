# SPEC: tests/conftest.py

## Purpose
Shared fixtures used across all test files. Sets up test isolation properly.

## Key Fixtures

### `settings` (function scope)
```python
@pytest.fixture
def settings():
    """Override settings for test environment."""
    return Settings(
        database_url="postgresql+asyncpg://memora:memora@localhost:5432/memora_test",
        contradiction_threshold=0.75,
        top_k_retrieval=3,
        context_window_budget=2000,
        embedding_dim=384,
        use_networkx_fallback=True,   # Skip Neo4j in unit tests
        anthropic_api_key="test-key",
    )
```

### `clean_bus` (function scope)
```python
@pytest.fixture
def clean_bus():
    """Reset event bus between tests. Critical for test isolation."""
    from memora.core.events import bus
    yield bus
    bus.clear()   # Always clear after each test
```

### `mock_llm` (function scope)
```python
@pytest.fixture
def mock_llm():
    """
    Mock LLM that returns configurable responses.
    Default: returns valid JSON for judge prompts with score=0.1 (no contradiction).
    """
    class MockLLM(ILLM):
        def __init__(self):
            self.responses = {}  # prompt_key → response
            self.calls = []      # Captured calls for assertion

        async def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
            self.calls.append({"system": system, "user": user})
            return self.responses.get("default", "Mock response")

        async def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 1000) -> dict:
            self.calls.append({"system": system, "user": user, "json": True})
            return self.responses.get("json", {
                "contradiction_score": 0.10,
                "reasoning": "No contradiction found",
                "suggested_resolution": "accept"
            })

    return MockLLM()
```

### `mock_embedder` (function scope)
```python
@pytest.fixture
def mock_embedder():
    """Returns deterministic embeddings based on text hash. 384 dims, unit normalized."""
    class MockEmbedder(IEmbeddingModel):
        async def embed(self, text: str) -> list[float]:
            # Deterministic: same text → same embedding
            seed = hash(text) % 10000
            rng = random.Random(seed)
            v = [rng.gauss(0, 1) for _ in range(384)]
            # Normalize
            norm = sum(x**2 for x in v) ** 0.5
            return [x/norm for x in v]

        async def embed_batch(self, texts: list[str]) -> list[list[float]]:
            return [await self.embed(t) for t in texts]

    return MockEmbedder()
```

### `mock_vector_store` (function scope)
```python
@pytest.fixture
def mock_vector_store(mock_embedder):
    """In-memory vector store for tests. No DB required."""
    class InMemoryVectorStore(IVectorSearch):
        def __init__(self):
            self._cubes: dict[str, tuple[MemCube, list[float]]] = {}

        async def upsert(self, cube: MemCube) -> None:
            self._cubes[cube.id] = (cube, cube.embedding or [])

        async def similarity_search(self, query_embedding, top_k=5, memory_types=None):
            results = []
            for cube, emb in self._cubes.values():
                if memory_types and cube.memory_type not in memory_types:
                    continue
                if not emb:
                    continue
                score = cosine_similarity(query_embedding, emb)
                results.append((cube, score))
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]

    return InMemoryVectorStore()
```

### `mock_failure_log` (function scope)
```python
@pytest.fixture
def mock_failure_log():
    class InMemoryFailureLog(IFailureLog):
        def __init__(self):
            self.entries = []

        async def log(self, action, memory_ids, feedback, session_id):
            entry_id = str(uuid4())
            self.entries.append({
                "id": entry_id, "action": action,
                "memory_ids": memory_ids, "feedback": feedback
            })
            return entry_id

        async def get_patterns(self):
            from collections import Counter
            counter = Counter()
            for entry in self.entries:
                for mid in entry["memory_ids"]:
                    counter[mid] += 1
            return [{"cube_id": k, "failure_count": v, "last_failure_at": datetime.utcnow()}
                    for k, v in counter.items()]

    return InMemoryFailureLog()
```

### `cube_factory` (function scope)
```python
@pytest.fixture
def cube_factory(mock_embedder, settings):
    return MemCubeFactory(mock_embedder, settings)
```

### `sample_cubes` (function scope)
```python
@pytest.fixture
def sample_cubes(cube_factory):
    """Pre-built MemCubes for testing. Returns dict[str, MemCube]."""
    import asyncio
    loop = asyncio.get_event_loop()
    return {
        "pricing_low": loop.run_until_complete(cube_factory.create(
            content="User prefers low-cost B2B pricing model",
            memory_type=MemoryType.SEMANTIC,
            session_id="test-session",
            tags=["pricing", "B2B"]
        )),
        "pricing_premium": loop.run_until_complete(cube_factory.create(
            content="User wants to pursue premium pricing strategy",
            memory_type=MemoryType.SEMANTIC,
            session_id="test-session",
            tags=["pricing", "premium"]
        )),
        "episode_1": loop.run_until_complete(cube_factory.create(
            content="User: Let's discuss pricing. Agent: Sure, what model do you prefer?",
            memory_type=MemoryType.EPISODIC,
            session_id="test-session",
            tags=["pricing"]
        )),
    }
```

---

# SPEC: tests/unit/test_mem_cube.py

## What to test: `core/types.py`, `vault/mem_cube.py`, `vault/provenance.py`

```python
class TestMemCubeValidation:
    def test_empty_content_raises(self): ...
    def test_auto_id_generation(self): ...
    def test_embedding_wrong_dim_raises(self): ...
    def test_negative_access_count_raises(self): ...
    def test_to_dict_serializes_enums_as_strings(self): ...
    def test_from_dict_restores_enums(self): ...
    def test_round_trip_dict(self): ...

class TestProvenance:
    def test_new_sets_version_1(self): ...
    def test_new_sets_parent_id_none(self): ...
    def test_invalid_origin_raises(self): ...
    def test_bump_version_increments(self): ...
    def test_bump_version_preserves_created_at(self): ...
    def test_serialize_deserialize_round_trip(self): ...

class TestMemCubeFactory:
    async def test_create_embeds_content(self, cube_factory, mock_embedder): ...
    async def test_create_sets_provenance(self, cube_factory): ...
    async def test_create_empty_content_raises(self, cube_factory): ...
    async def test_create_version_increments_version_number(self, cube_factory): ...
    async def test_create_version_sets_parent_id(self, cube_factory): ...
    def test_to_db_row_all_fields_present(self, cube_factory, sample_cubes): ...
    def test_from_db_row_restores_provenance(self, cube_factory, sample_cubes): ...

class TestContradictionVerdict:
    def test_score_out_of_range_high(self): ...
    def test_score_out_of_range_low(self): ...
    def test_is_quarantined_at_threshold(self): ...
    def test_is_quarantined_above_threshold(self): ...
    def test_is_cleared_below_threshold(self): ...

class TestEpisode:
    def test_end_before_start_raises(self): ...
    def test_boundary_score_out_of_range_raises(self): ...
    def test_empty_content_raises(self): ...
```

---

# SPEC: tests/unit/test_episode_segmenter.py

## What to test: `scheduler/boundary_detector.py`, `scheduler/episode_segmenter.py`

```python
class TestBoundaryDetector:
    async def test_same_topic_low_shift(self, mock_embedder):
        """Two sentences about pricing → shift score < 0.3"""
        ...

    async def test_different_topic_high_shift(self, mock_embedder):
        """Pricing → weather conversation → shift score > 0.6"""
        # Use embedder with known vectors for pricing vs weather

    async def test_buffer_overflow_forces_boundary(self, mock_embedder, settings):
        """After buffer_size turns, is_boundary always True regardless of shift"""
        settings.episode_buffer_size = 3
        detector = BoundaryDetector(mock_embedder, settings)
        history = ["turn1", "turn2", "turn3"]  # buffer full
        result = await detector.is_boundary(history, "related turn")
        assert result is True

    async def test_threshold_respected(self, mock_embedder, settings):
        settings.boundary_threshold = 0.9  # Very high threshold
        # Even somewhat different topics shouldn't trigger boundary
        ...

class TestEpisodeSegmenter:
    async def test_first_turn_no_episode(self, mock_embedder, settings):
        """First turn: buffer started, no episode returned"""
        segmenter = EpisodeSegmenter(BoundaryDetector(mock_embedder, settings))
        result = await segmenter.process_turn("Hello there", "session-1")
        assert result is None

    async def test_boundary_triggers_episode(self, mock_embedder, settings):
        """Topic shift → sealed episode returned"""
        ...

    async def test_episode_has_correct_turn_range(self, ...):
        """Episode.start_turn and end_turn match buffer contents"""
        ...

    async def test_flush_returns_remaining_buffer(self, ...):
        """flush() seals whatever is in buffer"""
        ...

    async def test_flush_empty_buffer_returns_none(self, ...):
        ...

    async def test_new_episode_starts_with_triggering_turn(self, ...):
        """After sealing, next buffer starts with the turn that triggered boundary"""
        ...
```

---

# SPEC: tests/unit/test_contradiction_detector.py

## What to test: `court/contradiction_detector.py`, `court/judge_agent.py`

(Full test list already specified in `specs/court/SPEC_court.md`)

Additional fixtures needed:
```python
@pytest.fixture
def detector():
    return ContradictionDetector(threshold=0.75)

@pytest.fixture
def judge_agent(mock_llm, mock_vector_store, mock_embedder, settings, clean_bus):
    return JudgeAgent(mock_llm, mock_vector_store, ContradictionDetector(0.75),
                      mock_embedder, settings, clean_bus)
```

---

# SPEC: tests/unit/test_tier_router.py

## What to test: `vault/tier_router.py`

```python
class TestTierRouter:
    @pytest.fixture
    def router(self, settings):
        return TierRouter(settings)

    def test_high_access_recent_is_hot(self, router, sample_cubes):
        cube = replace(sample_cubes["episode_1"],
                      access_count=15,
                      provenance=Provenance.new("user_input", "s1"))
        # Simulate last access 0.5 days ago via provenance.updated_at
        assert router.decide(cube) == MemoryTier.HOT

    def test_unaccessed_new_is_warm(self, router, sample_cubes):
        # access_count=0, created_at=now
        assert router.decide(sample_cubes["episode_1"]) == MemoryTier.WARM

    def test_unaccessed_old_is_cold(self, router):
        # access_count=0, created 10 days ago
        old_cube = make_old_cube(days=10)
        assert router.decide(old_cube) == MemoryTier.COLD

    def test_should_promote_warm_to_hot(self, router): ...
    def test_should_demote_warm_to_cold(self, router): ...
    def test_no_change_needed(self, router): ...

    @pytest.mark.parametrize("access_count,days,expected_tier", [
        (15, 0.5, MemoryTier.HOT),
        (3, 2, MemoryTier.WARM),
        (0, 10, MemoryTier.COLD),
        (0, 3, MemoryTier.WARM),   # New enough to stay warm
        (1, 8, MemoryTier.WARM),   # Has been accessed, recent-ish
    ])
    def test_parametrized_tier_decisions(self, router, access_count, days, expected_tier): ...
```

---

# SPEC: tests/unit/test_hybrid_retriever.py

(Full test list already in `specs/retrieval/SPEC_retrieval.md`)

Additional setup:
```python
@pytest.fixture
def hybrid_retriever(mock_vector_store, mock_embedder, settings, mock_failure_log):
    dense = DenseRetriever(mock_vector_store, mock_embedder)
    symbolic = MockSymbolicRetriever()  # In-memory tag store
    expander = QueryExpander(MockKGRepo(), symbolic)
    experience_learner = ExperienceLearner(mock_failure_log)
    reranker = Reranker(experience_learner, settings)
    return HybridRetriever(dense, symbolic, expander, reranker, settings)
```

---

# SPEC: tests/unit/test_experience_learner.py

(Full test list already in `specs/agent/SPEC_agent_llm_experience.md`)

---

# SPEC: tests/integration/test_ingestion_pipeline.py

## Requires: Real PostgreSQL test DB + event bus

```python
@pytest.mark.integration
class TestIngestionPipeline:
    @pytest.fixture(autouse=True)
    async def setup(self, settings, mock_llm, mock_embedder):
        # Setup real DB, real components, mock LLM and embedder
        self.captured_events = []
        clean_bus.subscribe(MemoryWriteRequested,
                           lambda e: self.captured_events.append(e))
        yield
        clean_bus.clear()

    async def test_single_turn_no_episode(self): ...
    async def test_boundary_triggers_write(self): ...
    async def test_buffer_overflow_triggers_write(self): ...
    async def test_predict_calibrate_deduplication(self): ...
    async def test_classifier_fallback_on_llm_error(self): ...
    async def test_multiple_memory_types_from_one_episode(self):
        """Episode about pricing → both EPISODIC and SEMANTIC cubes published"""
        ...
```

---

# SPEC: tests/integration/test_court_to_vault.py

```python
@pytest.mark.integration
class TestCourtToVaultFlow:
    """Tests the full Court → Vault pipeline via events."""

    async def test_approved_memory_reaches_vault(self):
        """MemoryWriteRequested → JudgeAgent approves → Vault persists"""
        # Setup: empty vault, low-score mock LLM response (score=0.1)
        # Publish MemoryWriteRequested
        # Wait for event propagation (await asyncio.sleep(0.1))
        # Assert: cube_id exists in episodic_repo
        ...

    async def test_quarantined_memory_in_pending_queue(self):
        """MemoryWriteRequested → JudgeAgent quarantines → QuarantineRepo has record"""
        # Setup: pre-populate vault with conflicting memory
        # Mock LLM to return score=0.9
        # Publish MemoryWriteRequested
        # Assert: quarantine_repo.list_pending() has 1 item
        ...

    async def test_accept_resolution_writes_to_vault(self):
        """User accepts quarantined memory → Vault stores it"""
        # Setup: create quarantine record
        # Call resolution_handler.resolve(id, RESOLVED_ACCEPT)
        # Assert: cube in vault
        ...

    async def test_reject_resolution_discards_memory(self):
        """User rejects → memory NOT in vault"""
        ...

    async def test_merge_resolution_writes_merged_content(self):
        """User merges → vault has merged content, not original"""
        merged = "User prefers flexible pricing with premium option"
        # resolution_handler.resolve(id, RESOLVED_MERGE, merged_content=merged)
        # Assert: vault has cube with content==merged
        ...

    async def test_double_resolve_raises(self):
        # Resolve once → success
        # Resolve again → AlreadyResolvedError
        ...

    async def test_graph_updated_for_kg_node_memories(self):
        # Approve a KG_NODE type memory
        # Assert: kg_repo.get_all_nodes() includes new node
        ...
```

---

# SPEC: tests/e2e/test_demo_scenario.py

## Purpose
The killer demo script as an automated test.
This is the end-to-end validation that the whole system works together.

```python
@pytest.mark.e2e
class TestDemoScenario:
    """
    Reproduces the exact demo scenario:
    1. Set low-cost strategy → stored
    2. Shift to premium → Court fires
    3. Resolve → memory updated
    4. Ask about past failures → Experience Learner responds
    5. Graph updates throughout
    """

    @pytest.fixture(autouse=True)
    async def setup(self, real_app):
        """Starts full FastAPI test client with real components (mock LLM)."""
        async with AsyncClient(app=real_app, base_url="http://test") as client:
            self.client = client
            resp = await client.post("/chat/session")
            self.session_id = resp.json()["session_id"]

    async def test_step_1_first_message_creates_memory(self):
        """Chat → ConversationTurnEvent → IngestionPipeline → MemoryWriteRequested → Court approves → Vault"""
        resp = await self.client.post("/chat", json={
            "message": "We're building a low-cost B2B product targeting SMBs.",
            "session_id": self.session_id
        })
        assert resp.status_code == 200
        await asyncio.sleep(0.5)  # Allow async event propagation

        # Memory should now be in vault
        memories = await self.client.get(f"/memories?session_id={self.session_id}")
        assert memories.json()["total"] >= 1

    async def test_step_2_contradiction_triggers_court(self):
        """Contradictory message → Court quarantines"""
        # First establish a memory
        await self.client.post("/chat", json={
            "message": "Our pricing model is definitely low-cost.",
            "session_id": self.session_id
        })
        await asyncio.sleep(0.5)

        # Now contradict it — mock LLM configured to return high contradiction score
        await self.client.post("/chat", json={
            "message": "Let's shift to a premium enterprise pricing strategy.",
            "session_id": self.session_id
        })
        await asyncio.sleep(0.5)

        # Court queue should have a pending item
        court_resp = await self.client.get("/court/queue")
        assert len(court_resp.json()) >= 1
        assert court_resp.json()[0]["contradiction_score"] >= 0.75

    async def test_step_3_resolve_updates_memory(self):
        """Resolve quarantine → memory in vault"""
        # Get quarantine item
        court_resp = await self.client.get("/court/queue")
        q_id = court_resp.json()[0]["quarantine_id"]

        # Accept resolution
        resolve_resp = await self.client.post(f"/court/resolve/{q_id}", json={
            "resolution": "accept"
        })
        assert resolve_resp.status_code == 200

        # Queue should be empty
        await asyncio.sleep(0.1)
        court_resp = await self.client.get("/court/queue")
        assert len(court_resp.json()) == 0

    async def test_step_4_graph_has_nodes(self):
        """After conversation, KG should have nodes"""
        graph_resp = await self.client.get("/graph/nodes")
        assert len(graph_resp.json()["nodes"]) >= 1

    async def test_step_5_health_shows_memories(self):
        """Health panel shows non-zero memory count"""
        health_resp = await self.client.get("/health")
        assert health_resp.json()["total_memories"] >= 1
        assert health_resp.json()["status"] == "ok"

    async def test_full_demo_flow_sequential(self):
        """Run all 5 steps as one sequential test — the actual demo script"""
        # Steps 1-5 in sequence, assertions at each step
        # This is the definitive "does the demo work" test
        ...
```

---

# SPEC: scripts/seed_demo_data.py

## Purpose
Pre-populate the database with demo memories so the graph visualizer looks good on launch.

## Expected output after running:
- 8 episodic memories from a fictional "Acme Corp product strategy" session
- 6 semantic memories (pricing, team, product decisions)
- 4 KG nodes connected in a meaningful subgraph
- 1 pending quarantine record (pre-seeded contradiction for live demo)

## Data to seed:
```python
DEMO_MEMORIES = [
    ("episodic", "We decided to target B2B SMB market for our initial product launch.", ["strategy", "market"]),
    ("semantic", "Target market: B2B small-to-medium businesses", ["market"], "product.target_market"),
    ("episodic", "Team size: 4 engineers, 1 designer, 1 PM. Timeline: 6 months.", ["team", "planning"]),
    ("semantic", "Team composition: 4 eng, 1 design, 1 PM", ["team"], "team.composition"),
    ("episodic", "Pricing discussion: decided on freemium model with $29/month pro tier.", ["pricing"]),
    ("semantic", "Pricing model: freemium with $29/month pro tier", ["pricing"], "product.pricing_model"),
    ("episodic", "Tech stack chosen: FastAPI, PostgreSQL, React. Deploy on AWS.", ["technical"]),
    ("semantic", "Tech stack: FastAPI + PostgreSQL + React on AWS", ["technical"], "product.tech_stack"),
]

# The pre-seeded contradiction (for live demo):
DEMO_QUARANTINE = {
    "incoming": "User now wants to charge $99/month enterprise pricing instead of $29",
    "conflicting": "Pricing model: freemium with $29/month pro tier",
    "score": 0.88,
    "reasoning": "Incoming memory directly contradicts the established pricing of $29/month",
}
```

# SPEC: core/interfaces.py

## Purpose
Abstract base classes (ports) for every repository and service.
Modules depend on these interfaces, never on concrete implementations.
This is the foundation of the dependency inversion that allows mocking in tests.

## File Location
`memora/core/interfaces.py`

## Dependencies
- `memora.core.types` only

---

## Interfaces to Implement

### `IEpisodicRepo`
```python
class IEpisodicRepo(ABC):
    @abstractmethod
    async def save(self, cube: MemCube) -> str:
        """Persist an episodic MemCube. Returns the cube.id."""

    @abstractmethod
    async def get(self, cube_id: str) -> Optional[MemCube]:
        """Fetch by ID. Returns None if not found."""

    @abstractmethod
    async def delete(self, cube_id: str) -> None:
        """Hard delete. Raises MemoryNotFoundError if not found."""

    @abstractmethod
    async def list_recent(self, session_id: str, limit: int = 20) -> list[MemCube]:
        """Return most recent N episodic memories for a session, newest first."""

    @abstractmethod
    async def update_access(self, cube_id: str) -> None:
        """Increment access_count and update provenance.updated_at."""
```

### `ISemanticRepo`
```python
class ISemanticRepo(ABC):
    @abstractmethod
    async def save(self, cube: MemCube) -> str: ...

    @abstractmethod
    async def get(self, cube_id: str) -> Optional[MemCube]: ...

    @abstractmethod
    async def delete(self, cube_id: str) -> None: ...

    @abstractmethod
    async def upsert_by_key(self, key: str, cube: MemCube) -> str:
        """Upsert: if a semantic memory with this key exists, update it. Otherwise insert."""
```

### `IKGRepo`
```python
class IKGRepo(ABC):
    @abstractmethod
    async def upsert_node(self, cube: MemCube) -> str:
        """Insert or update a KG node. Returns node ID."""

    @abstractmethod
    async def add_edge(self, from_id: str, to_id: str, label: str,
                       metadata: dict | None = None) -> str:
        """Add a directed edge. Returns edge ID. Old edges are archived, not deleted."""

    @abstractmethod
    async def deprecate_edge(self, edge_id: str, reason: str) -> None:
        """Mark edge as deprecated with a reason and deprecated_at timestamp."""

    @abstractmethod
    async def get_neighbors(self, cube_id: str, depth: int = 1) -> list[MemCube]:
        """Return all nodes reachable within `depth` hops. Active edges only."""

    @abstractmethod
    async def get_all_nodes(self) -> list[dict]:
        """For graph visualization. Returns list of {id, label, type, tier}."""

    @abstractmethod
    async def get_all_edges(self) -> list[dict]:
        """For graph visualization. Returns list of {id, from, to, label, active, deprecated_at}."""
```

### `IQuarantineRepo`
```python
class IQuarantineRepo(ABC):
    @abstractmethod
    async def save_pending(self, cube: MemCube,
                           verdict: ContradictionVerdict) -> str:
        """Store a quarantined memory. Returns quarantine_id."""

    @abstractmethod
    async def list_pending(self) -> list[dict]:
        """Return all PENDING quarantine records with their verdicts."""

    @abstractmethod
    async def get(self, quarantine_id: str) -> Optional[dict]:
        """Fetch a specific quarantine record."""

    @abstractmethod
    async def resolve(self, quarantine_id: str, status: QuarantineStatus,
                      merged_content: str = "") -> None:
        """Mark as resolved. Raises QuarantineNotFoundError if not found."""
```

### `IVectorSearch`
```python
class IVectorSearch(ABC):
    @abstractmethod
    async def similarity_search(self, query_embedding: list[float],
                                top_k: int = 5,
                                memory_types: list[MemoryType] | None = None) -> list[tuple[MemCube, float]]:
        """
        Return top_k MemCubes most similar to query_embedding.
        Each result is (MemCube, cosine_similarity_score).
        Optional filter by memory_types.
        """
```

### `IFailureLog`
```python
class IFailureLog(ABC):
    @abstractmethod
    async def log(self, action: str, memory_ids: list[str], feedback: str,
                  session_id: str) -> str:
        """Record a failure. Returns failure_log_id."""

    @abstractmethod
    async def get_patterns(self) -> list[dict]:
        """
        Return list of failure patterns:
        [{memory_cluster_ids: [...], failure_count: int, last_failure_at: datetime}]
        """
```

### `IEmbeddingModel`
```python
class IEmbeddingModel(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return 384-dim embedding for text."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return batch of embeddings. More efficient than calling embed() in a loop."""
```

### `ILLM`
```python
class ILLM(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str,
                       max_tokens: int = 1000) -> str:
        """Single-turn completion. Returns assistant message text."""

    @abstractmethod
    async def complete_json(self, system: str, user: str,
                            schema: dict, max_tokens: int = 1000) -> dict:
        """
        Completion that MUST return valid JSON matching schema.
        Raises LLMResponseError if response cannot be parsed as valid JSON.
        """
```

---

# SPEC: core/errors.py

## Purpose
All domain exceptions. Using typed exceptions (not generic `ValueError` or `RuntimeError`)
makes error handling explicit, testable, and readable.

## File Location
`memora/core/errors.py`

---

## Exceptions to Implement

```python
class MemoraError(Exception):
    """Base class for all MEMORA exceptions."""

# Memory operations
class MemoryNotFoundError(MemoraError):
    """Raised when a MemCube ID does not exist in any repository."""
    def __init__(self, cube_id: str):
        super().__init__(f"Memory not found: {cube_id}")
        self.cube_id = cube_id

class MemoryValidationError(MemoraError):
    """Raised when a MemCube fails validation (empty content, bad embedding dim, etc.)."""

class DuplicateMemoryError(MemoraError):
    """Raised on attempt to insert a MemCube with an ID that already exists."""
    def __init__(self, cube_id: str):
        super().__init__(f"Memory already exists: {cube_id}")
        self.cube_id = cube_id

# Quarantine operations
class QuarantineNotFoundError(MemoraError):
    """Raised when a quarantine_id does not exist."""
    def __init__(self, quarantine_id: str):
        super().__init__(f"Quarantine record not found: {quarantine_id}")
        self.quarantine_id = quarantine_id

class AlreadyResolvedError(MemoraError):
    """Raised on attempt to resolve an already-resolved quarantine record."""

# LLM errors
class LLMResponseError(MemoraError):
    """Raised when LLM returns unparseable or invalid response."""
    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response

class LLMRateLimitError(MemoraError):
    """Raised on 429 from LLM provider. Caller should retry with backoff."""

# Storage errors
class StorageConnectionError(MemoraError):
    """Raised when DB connection cannot be established."""

class EmbeddingDimensionError(MemoraError):
    """Raised when embedding vector has wrong dimension."""
    def __init__(self, expected: int, got: int):
        super().__init__(f"Embedding dimension mismatch: expected {expected}, got {got}")
        self.expected = expected
        self.got = got

# Court errors
class ContradictionDetectionError(MemoraError):
    """Raised when contradiction detection pipeline fails (not the same as finding a contradiction)."""
```

---

# SPEC: core/config.py

## Purpose
Single source of truth for all configuration. Reads from environment variables and `.env` file.

## File Location
`memora/core/config.py`

---

## Settings Model

```python
class Settings(BaseSettings):
    # LLM providers
    groq_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = "groq"     # "groq" | "openai"
    llm_model: str = "llama3-70b-8192"  # Model string

    # Databases
    database_url: str = "postgresql+asyncpg://memora:memora@localhost:5432/memora"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "memorapass"
    redis_url: str = "redis://localhost:6379"
    use_networkx_fallback: bool = False  # Use NetworkX instead of Neo4j (demo/offline mode)

    # Memory Court
    contradiction_threshold: float = 0.75   # [0.0, 1.0]
    court_retrieval_top_k: int = 3           # How many existing memories to check against

    # Retrieval
    top_k_retrieval: int = 5
    context_window_budget: int = 8000        # tokens before MemGPT pager evicts
    dense_weight: float = 0.7                # Weight for dense score in hybrid fusion
    symbolic_weight: float = 0.3             # Weight for symbolic score in hybrid fusion
    failure_penalty: float = 0.4             # Score multiplier for known-bad memory clusters

    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Episode segmentation
    episode_buffer_size: int = 5             # Max turns before forced episode boundary
    boundary_threshold: float = 0.4          # Semantic shift score to trigger boundary

    # TTL
    hot_tier_ttl_seconds: int = 86400        # 24h
    cold_tier_threshold_days: int = 7        # Move to cold after 7 days no access

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

**Constraints:**
- `contradiction_threshold` MUST be validated: 0.0 ≤ value ≤ 1.0
- `dense_weight + symbolic_weight` MUST equal 1.0 (validated in post-init)
- `embedding_dim` MUST be 384 (the all-MiniLM-L6-v2 output dimension)

**Factory:**
```python
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

The `@lru_cache` means settings are read once per process. Tests override via environment variables.

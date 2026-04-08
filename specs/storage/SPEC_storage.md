# SPEC: storage/ — All Storage Layer Files

## Module Purpose
Raw database drivers and schema definitions. Zero business logic.
Vault and retrieval modules call these through the interfaces in `core/interfaces.py`.

---

# SPEC: storage/postgres/connection.py

## Purpose
SQLAlchemy async engine factory. Single connection pool for the whole app.

## Functions to Implement

```python
async def create_engine(database_url: str) -> AsyncEngine:
    """
    Create and return SQLAlchemy async engine.
    Pool config: pool_size=10, max_overflow=20, pool_timeout=30s.
    """

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager yielding a database session.
    Used as FastAPI dependency via `Depends(get_session)`.
    Auto-commits on success, auto-rolls back on exception.
    """

async def dispose_engine() -> None:
    """Gracefully close all connections. Called on app shutdown."""
```

**Error handling:**
- If connection fails on startup, raise `StorageConnectionError` with the DSN (redacted password)

---

# SPEC: storage/postgres/models.py

## Purpose
SQLAlchemy ORM models. These are the DB schema definitions.

## Tables to Define

### `mem_cubes`
```sql
CREATE TABLE mem_cubes (
    id            VARCHAR(36)   PRIMARY KEY,
    content       TEXT          NOT NULL,
    memory_type   VARCHAR(20)   NOT NULL,  -- MemoryType enum value
    tier          VARCHAR(10)   NOT NULL,  -- MemoryTier enum value
    tags          JSONB         NOT NULL DEFAULT '[]',
    embedding     vector(384),             -- pgvector column
    provenance    JSONB         NOT NULL,  -- Serialized Provenance
    access_count  INTEGER       NOT NULL DEFAULT 0,
    ttl_seconds   INTEGER,
    extra         JSONB         NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX mem_cubes_type_idx ON mem_cubes(memory_type);
CREATE INDEX mem_cubes_tier_idx ON mem_cubes(tier);
CREATE INDEX mem_cubes_tags_idx ON mem_cubes USING GIN(tags);
CREATE INDEX mem_cubes_embedding_idx ON mem_cubes USING ivfflat (embedding vector_cosine_ops);
```

### `quarantine_records`
```sql
CREATE TABLE quarantine_records (
    id               VARCHAR(36)   PRIMARY KEY,
    incoming_cube_id VARCHAR(36)   NOT NULL,
    conflicting_id   VARCHAR(36)   NOT NULL,
    contradiction_score FLOAT     NOT NULL,
    reasoning        TEXT          NOT NULL,
    suggested_resolution TEXT,
    status           VARCHAR(30)   NOT NULL DEFAULT 'pending',
    merged_content   TEXT,
    incoming_cube_json JSONB       NOT NULL,  -- Full MemCube serialized
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    resolved_at      TIMESTAMPTZ
);
```

### `failure_log`
```sql
CREATE TABLE failure_log (
    id                 VARCHAR(36)   PRIMARY KEY,
    session_id         VARCHAR(36)   NOT NULL,
    action_description TEXT          NOT NULL,
    memory_cluster_ids JSONB         NOT NULL,  -- list of cube IDs
    feedback           TEXT          NOT NULL,
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX failure_log_session_idx ON failure_log(session_id);
```

### `timeline_events`
```sql
CREATE TABLE timeline_events (
    id          VARCHAR(36)   PRIMARY KEY,
    cube_id     VARCHAR(36),
    event_type  VARCHAR(30)   NOT NULL,  -- "created"|"updated"|"quarantined"|"resolved"|"evicted"
    description TEXT,
    session_id  VARCHAR(36),
    metadata    JSONB         NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX timeline_session_idx ON timeline_events(session_id);
CREATE INDEX timeline_created_idx ON timeline_events(created_at DESC);
```

## ORM Model Classes

Each table gets a corresponding SQLAlchemy `DeclarativeBase` model:
- `MemCubeRow` → `mem_cubes`
- `QuarantineRow` → `quarantine_records`
- `FailureLogRow` → `failure_log`
- `TimelineEventRow` → `timeline_events`

---

# SPEC: storage/postgres/migrations/versions/001_init.py

## Purpose
Alembic migration that creates all four tables from scratch.
Enable pgvector extension before creating tables.

```python
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Create mem_cubes, quarantine_records, failure_log, timeline_events
    # Create all indexes
    ...

def downgrade() -> None:
    # Drop all tables in reverse dependency order
    # Drop pgvector extension
    ...
```

---

# SPEC: storage/vector/embedding.py

## Purpose
Wrapper around sentence-transformers. Implements `IEmbeddingModel`.

## Class: `SentenceTransformerEmbedder`

```python
class SentenceTransformerEmbedder(IEmbeddingModel):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Load model on init. Log loading time."""
        ...

    async def embed(self, text: str) -> list[float]:
        """
        Embed a single text string.
        - Truncate input to 512 tokens (model limit)
        - Return list of 384 floats
        - Normalize to unit length (for cosine similarity)
        - MUST be run in a thread pool (model.encode is CPU-bound, not async)
        """
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple texts in one model call.
        - More efficient than calling embed() in a loop
        - Returns list in same order as input
        - Each embedding is normalized to unit length
        """
        ...
```

**Performance constraint:** Single embed call MUST complete in < 200ms on CPU.

---

# SPEC: storage/vector/pgvector_client.py

## Purpose
pgvector-specific upsert and cosine similarity search. Implements `IVectorSearch`.

## Class: `PgVectorClient`

```python
class PgVectorClient(IVectorSearch):
    def __init__(self, session_factory: Callable[[], AsyncSession]):
        ...

    async def upsert(self, cube: MemCube) -> None:
        """
        Insert or update MemCube in mem_cubes table.
        Uses PostgreSQL ON CONFLICT DO UPDATE.
        Raises EmbeddingDimensionError if embedding is not 384-dim.
        """
        ...

    async def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        memory_types: list[MemoryType] | None = None
    ) -> list[tuple[MemCube, float]]:
        """
        Cosine similarity search using pgvector <=> operator.
        Returns list of (MemCube, score) sorted by score DESC.
        Optional filter: only return memories of specified types.
        Skips MemCubes with NULL embeddings.
        """
        ...

    async def delete(self, cube_id: str) -> None:
        """Hard delete. Raises MemoryNotFoundError if not found."""
        ...
```

**SQL for similarity search:**
```sql
SELECT *, 1 - (embedding <=> $1::vector) AS score
FROM mem_cubes
WHERE embedding IS NOT NULL
  AND ($2::text[] IS NULL OR memory_type = ANY($2))
ORDER BY embedding <=> $1::vector
LIMIT $3
```

---

# SPEC: storage/graph/neo4j_client.py

## Purpose
Neo4j async driver wrapper. Implements `IKGRepo` for production use.

## Class: `Neo4jClient`

```python
class Neo4jClient(IKGRepo):
    def __init__(self, uri: str, user: str, password: str):
        """Connect using neo4j async driver."""
        ...

    async def upsert_node(self, cube: MemCube) -> str:
        """
        MERGE node on cube.id.
        Sets: id, content, memory_type, tier, tags, access_count, updated_at.
        Returns cube.id.
        """
        ...

    async def add_edge(self, from_id: str, to_id: str, label: str,
                       metadata: dict | None = None) -> str:
        """
        Create directed relationship.
        Edge has: id (UUID), label, active=True, created_at, metadata.
        IMPORTANT: Does NOT deprecate existing edges with same label — edges accumulate
        to form the version history. Deprecation is explicit via deprecate_edge().
        """
        ...

    async def deprecate_edge(self, edge_id: str, reason: str) -> None:
        """Set active=False, deprecated_at=NOW(), deprecation_reason=reason."""
        ...

    async def get_neighbors(self, cube_id: str, depth: int = 1) -> list[MemCube]:
        """
        Traverse active edges only (WHERE r.active = true).
        Return all nodes within `depth` hops.
        """
        ...

    async def get_all_nodes(self) -> list[dict]:
        """Returns all nodes as dicts for D3 visualization."""
        ...

    async def get_all_edges(self) -> list[dict]:
        """Returns all edges (active and deprecated) for D3 visualization."""
        ...
```

---

# SPEC: storage/graph/networkx_client.py

## Purpose
In-memory NetworkX fallback. Same interface as Neo4j. Used when `use_networkx_fallback=True`.
This enables demo/development without running Neo4j.

## Class: `NetworkXClient`

Identical interface to `Neo4jClient`. Internal state: `nx.DiGraph` instance.

**Key difference:** Data is NOT persisted between process restarts. Suitable for demo only.

Edge deprecation: set `graph.edges[from_id, to_id]['active'] = False`.

---

## Storage Module Integration Test Requirements

### test: postgres connection
- Connect to test DB
- Run migrations
- Verify all 4 tables exist

### test: pgvector upsert + search
- Insert MemCube with known embedding
- Search with identical embedding → score should be ≥ 0.99
- Search with orthogonal embedding → score should be ≤ 0.1

### test: graph upsert + traverse
- Insert 3 nodes: A → B → C
- get_neighbors(A, depth=1) → [B]
- get_neighbors(A, depth=2) → [B, C]

### test: quarantine lifecycle
- save_pending → list_pending shows 1 record
- resolve(RESOLVED_ACCEPT) → list_pending shows 0 records
- resolve same ID again → AlreadyResolvedError

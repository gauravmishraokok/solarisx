# SPEC: vault/ — All Vault Module Files

## Module Purpose
The MemCube abstraction layer. Owns: creation, persistence, tier routing, provenance, TTL.
Depends on: `core/`, `storage/` (via interfaces).
Does NOT know about: `court/`, `scheduler/`, `agent/`.

---

# SPEC: vault/mem_cube.py

## Purpose
MemCube factory and serialization helpers. The single place where MemCubes are born.

## Class: `MemCubeFactory`

```python
class MemCubeFactory:
    def __init__(self, embedding_model: IEmbeddingModel, settings: Settings):
        self.embedder = embedding_model
        self.settings = settings
```

### Methods

#### `async create(...) -> MemCube`
```python
async def create(
    self,
    content: str,
    memory_type: MemoryType,
    session_id: str,
    origin: str = "agent_inference",
    tags: list[str] | None = None,
    extra: dict | None = None,
    cube_id: str | None = None,       # If None, auto-generate UUID4
) -> MemCube:
```

**Behaviour:**
1. Validate: `content` must not be empty → raise `MemoryValidationError`
2. Validate: `origin` must be one of allowed values → raise `MemoryValidationError`
3. Generate `id` if not provided
4. Create `Provenance.new(origin, session_id)`
5. Compute embedding via `self.embedder.embed(content)`
6. Build and return `MemCube`

**Output:** Fully populated MemCube with embedding, provenance, default tier=WARM

---

#### `to_db_row(cube: MemCube) -> dict`
**Purpose:** Serialize MemCube to flat dict suitable for SQLAlchemy.

```python
def to_db_row(self, cube: MemCube) -> dict:
    return {
        "id": cube.id,
        "content": cube.content,
        "memory_type": cube.memory_type.value,
        "tier": cube.tier.value,
        "tags": cube.tags,           # Already a list, stored as JSONB
        "embedding": cube.embedding, # pgvector handles list[float]
        "provenance": asdict(cube.provenance) if cube.provenance else None,
        "access_count": cube.access_count,
        "ttl_seconds": cube.ttl_seconds,
        "extra": cube.extra,
    }
```

---

#### `from_db_row(row: dict) -> MemCube`
**Purpose:** Deserialize from SQLAlchemy row dict back to MemCube domain object.

Inverse of `to_db_row`. MUST reconstruct Provenance from JSONB, parse enum values.

---

#### `create_version(original: MemCube, new_content: str, session_id: str) -> MemCube`
**Purpose:** Create a new version of an existing MemCube. Used when a memory is updated.

**Behaviour:**
1. Generate new `id`
2. Set `provenance.parent_id = original.id`
3. Set `provenance.version = original.provenance.version + 1`
4. Recompute embedding for `new_content`
5. Return new MemCube (original is NOT modified)

---

# SPEC: vault/episodic_repo.py

## Purpose
CRUD for episodic memories backed by pgvector. Implements `IEpisodicRepo`.

## Class: `EpisodicRepo`

```python
class EpisodicRepo(IEpisodicRepo):
    def __init__(self, vector_client: PgVectorClient,
                 timeline_writer: "TimelineWriter"):
        ...
```

### Methods

#### `async save(cube: MemCube) -> str`
1. Validate `cube.memory_type == MemoryType.EPISODIC` → raise `MemoryValidationError` if wrong type
2. Call `vector_client.upsert(cube)`
3. Write `timeline_events` entry: `event_type="created"`, `cube_id=cube.id`
4. Return `cube.id`

#### `async get(cube_id: str) -> Optional[MemCube]`
Fetch from DB. Return None if not found (never raise on not-found).

#### `async delete(cube_id: str) -> None`
Hard delete. Call `vector_client.delete(cube_id)`. Write timeline entry: `event_type="evicted"`.
Raise `MemoryNotFoundError` if not found.

#### `async list_recent(session_id: str, limit: int = 20) -> list[MemCube]`
SQL: `SELECT * FROM mem_cubes WHERE memory_type='episodic' AND provenance->>'session_id'=$1 ORDER BY created_at DESC LIMIT $2`

#### `async update_access(cube_id: str) -> None`
`UPDATE mem_cubes SET access_count = access_count + 1, updated_at = NOW() WHERE id = $1`

---

# SPEC: vault/semantic_repo.py

## Purpose
CRUD for semantic/KV memories. Implements `ISemanticRepo`.
Semantic memories are indexed by a stable `key` string (e.g. "user.pricing_preference").

## Class: `SemanticRepo`

```python
class SemanticRepo(ISemanticRepo):
```

### `async upsert_by_key(key: str, cube: MemCube) -> str`
**Behaviour:**
1. Check if a semantic memory with `extra["key"] == key` already exists
2. If YES → create a new version using `MemCubeFactory.create_version()`, mark old version with `tier=COLD`
3. If NO → insert normally
4. Write timeline entry: `event_type="created"` or `event_type="updated"`
5. Return new `cube.id`

---

# SPEC: vault/kg_repo.py

## Purpose
CRUD for knowledge graph nodes and versioned edges. Implements `IKGRepo`.
Delegates to either `Neo4jClient` or `NetworkXClient` based on settings.

## Class: `KGRepo`

```python
class KGRepo(IKGRepo):
    def __init__(self, graph_client: IKGRepo, timeline_writer: "TimelineWriter"):
        self._client = graph_client  # Neo4j or NetworkX
        self._timeline = timeline_writer
```

All methods delegate to `self._client` + write timeline events.

**Timeline events for KG:**
- `upsert_node` → `event_type="created"` or `event_type="updated"`
- `add_edge` → `event_type="created"` with `metadata={"edge_label": label}`
- `deprecate_edge` → `event_type="updated"` with `metadata={"deprecated": True, "reason": reason}`

---

# SPEC: vault/quarantine_repo.py

## Purpose
CRUD for the quarantine bin. Implements `IQuarantineRepo`.

## Class: `QuarantineRepo`

```python
class QuarantineRepo(IQuarantineRepo):
```

### `async save_pending(cube: MemCube, verdict: ContradictionVerdict) -> str`
1. Generate `quarantine_id = uuid4()`
2. Serialize full `cube` as JSONB in `incoming_cube_json`
3. Set `status = QuarantineStatus.PENDING`
4. Write timeline entry: `event_type="quarantined"`, `cube_id=cube.id`
5. Return `quarantine_id`

### `async resolve(quarantine_id: str, status: QuarantineStatus, merged_content: str = "") -> None`
1. Fetch record → raise `QuarantineNotFoundError` if missing
2. If already resolved → raise `AlreadyResolvedError`
3. Update `status`, `resolved_at = NOW()`
4. If `RESOLVED_MERGE`: set `merged_content`
5. Write timeline entry: `event_type="resolved"`

---

# SPEC: vault/tier_router.py

## Purpose
Decision logic for which storage tier a MemCube should live in.
Single function + class. No DB calls. Pure logic.

## Function: `route_to_tier(cube: MemCube, settings: Settings) -> MemoryTier`

**Decision tree:**
```
IF cube.access_count >= 10 AND last access within 24h  → HOT
ELSE IF cube.access_count >= 1 OR created within 7 days → WARM
ELSE → COLD
```

## Class: `TierRouter`

```python
class TierRouter:
    def __init__(self, settings: Settings):
        ...

    def decide(self, cube: MemCube) -> MemoryTier:
        """Pure function. Returns the tier the cube SHOULD be in."""
        ...

    def should_promote(self, cube: MemCube) -> bool:
        """True if cube's current tier is lower than its decided tier."""
        ...

    def should_demote(self, cube: MemCube) -> bool:
        """True if cube's current tier is higher than its decided tier."""
        ...
```

**Test cases for tier_router:**
| access_count | days_since_access | current_tier | expected_decide |
|---|---|---|---|
| 15 | 0.5 | WARM | HOT |
| 3 | 2 | WARM | WARM |
| 0 | 10 | WARM | COLD |
| 0 | 3 | WARM | WARM (created within 7 days) |

---

# SPEC: vault/provenance.py

## Purpose
Helper functions for provenance management. Creates, updates, serializes Provenance objects.

## Functions

```python
def new_provenance(origin: str, session_id: str) -> Provenance:
    """Create fresh v1 Provenance. Validates origin value."""

def bump_version(p: Provenance, session_id: str) -> Provenance:
    """Return new Provenance with version+1, updated_at=now, parent_id unchanged."""

def serialize(p: Provenance) -> dict:
    """Convert to JSONB-serializable dict."""

def deserialize(data: dict) -> Provenance:
    """Reconstruct Provenance from JSONB dict."""
```

---

# SPEC: vault/ttl_manager.py

## Purpose
Periodic background task that enforces TTL expiry and tier transitions.
Runs every 60 seconds (configurable).

## Class: `TTLManager`

```python
class TTLManager:
    def __init__(self, episodic_repo: IEpisodicRepo,
                 semantic_repo: ISemanticRepo,
                 tier_router: TierRouter,
                 settings: Settings):
        ...

    async def run_cycle(self) -> dict:
        """
        Single maintenance cycle.
        Returns: {expired: int, promoted: int, demoted: int}
        """
        ...

    async def expire_ttl(self) -> int:
        """
        Delete MemCubes where ttl_seconds is set and
        (created_at + ttl_seconds * interval) < NOW().
        Returns count of deleted cubes.
        """
        ...

    async def rebalance_tiers(self) -> tuple[int, int]:
        """
        Re-evaluate tier for all non-cold MemCubes.
        Returns (promoted_count, demoted_count).
        """
        ...
```

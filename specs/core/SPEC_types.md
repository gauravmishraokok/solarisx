# SPEC: core/types.py

## Purpose
Central domain type definitions. The single source of truth for every data shape in the system.
Zero external dependencies. Every other module imports FROM here.

## File Location
`memora/core/types.py`

## Dependencies
- Python stdlib only: `dataclasses`, `enum`, `typing`, `datetime`, `uuid`
- NO imports from any other `memora/` module

---

## Types to Implement

### `MemoryType` (Enum)
**What it is:** Classifies what kind of memory a MemCube holds.

```python
class MemoryType(str, Enum):
    EPISODIC = "episodic"   # Narrative memory with temporal context (e.g. "On Tuesday we discussed pricing")
    SEMANTIC  = "semantic"  # Distilled fact (e.g. "User prefers low-cost B2B model")
    KG_NODE   = "kg_node"   # A knowledge graph entity node
    KG_EDGE   = "kg_edge"   # A knowledge graph relationship (stored separately for provenance)
```

**Constraints:**
- MUST be `str` mixin so it serializes cleanly to/from JSON and PostgreSQL VARCHAR
- MUST have exactly these four values

---

### `MemoryTier` (Enum)
**What it is:** Storage tier for the MemCube, determined by access frequency and age.

```python
class MemoryTier(str, Enum):
    HOT  = "hot"   # In-memory / KV-cache; accessed >10x in last 24h
    WARM = "warm"  # Active pgvector store; regular access
    COLD = "cold"  # Archived; not accessed in >7 days
```

**Constraints:**
- MUST be `str` mixin
- Tier transitions: HOT ↔ WARM ↔ COLD (managed by `vault/ttl_manager.py`)

---

### `QuarantineStatus` (Enum)
**What it is:** Lifecycle state of a memory held in the Memory Court quarantine bin.

```python
class QuarantineStatus(str, Enum):
    PENDING          = "pending"           # Awaiting human resolution
    RESOLVED_ACCEPT  = "resolved_accept"   # Accepted as-is, write to vault
    RESOLVED_REJECT  = "resolved_reject"   # Rejected, discard
    RESOLVED_MERGE   = "resolved_merge"    # Merged with conflicting memory, write merged version
```

---

### `Provenance` (Dataclass)
**What it is:** Immutable audit trail for every memory. Tracks origin, session, version chain.
Inspired by MemOS provenance tagging.

```python
@dataclass
class Provenance:
    origin: str          # "user_input" | "agent_inference" | "system" | "resolution"
    session_id: str      # UUID string of the conversation session
    created_at: datetime # UTC, auto-set on creation
    updated_at: datetime # UTC, auto-updated on every mutation
    version: int         # Starts at 1, increments on each update
    parent_id: Optional[str]  # cube_id of previous version (None for v1)
```

**Constraints:**
- `origin` MUST be one of: `"user_input"`, `"agent_inference"`, `"system"`, `"resolution"`
- `version` MUST start at 1 and only increment (never decrement)
- `parent_id` MUST be None when `version == 1`
- `created_at` MUST never be mutated after initialization
- `updated_at` MUST be set to `datetime.utcnow()` on every update

**Factory method:**
```python
@classmethod
def new(cls, origin: str, session_id: str) -> "Provenance":
    now = datetime.utcnow()
    return cls(origin=origin, session_id=session_id,
               created_at=now, updated_at=now, version=1, parent_id=None)
```

---

### `MemCube` (Dataclass)
**What it is:** The central memory unit. Every piece of information stored in the system is a MemCube.
Directly inspired by MemOS MemCube architecture.

```python
@dataclass
class MemCube:
    id: str                        # UUID string, auto-generated
    content: str                   # The actual memory text
    memory_type: MemoryType        # EPISODIC | SEMANTIC | KG_NODE | KG_EDGE
    tier: MemoryTier               # HOT | WARM | COLD
    tags: list[str]                # Flat list of string tags for symbolic filtering
    embedding: Optional[list[float]]  # Dense vector, 384-dim (all-MiniLM-L6-v2)
    provenance: Optional[Provenance]
    access_count: int              # Incremented on each retrieval
    ttl_seconds: Optional[int]     # None = no expiry
    extra: dict[str, Any]          # Flexible: KG edge labels, score metadata, etc.
```

**Constraints:**
- `id` MUST be auto-generated UUID4 string if not provided
- `content` MUST NOT be empty string on creation
- `embedding` length MUST be exactly 384 when not None
- `access_count` MUST be ≥ 0
- `tier` defaults to `MemoryTier.WARM`
- `tags` defaults to empty list (never None)
- `extra` defaults to empty dict (never None)

**Key methods to implement:**
```python
def bump_access(self) -> "MemCube":
    """Return new MemCube with access_count + 1 and provenance.updated_at refreshed."""
    ...

def with_embedding(self, embedding: list[float]) -> "MemCube":
    """Return new MemCube with embedding set. Validates length == 384."""
    ...

def to_dict(self) -> dict:
    """Serialize to plain dict (for JSON serialization). Converts enums to .value."""
    ...

@classmethod
def from_dict(cls, data: dict) -> "MemCube":
    """Deserialize from plain dict. Converts string values back to enums."""
    ...
```

---

### `Episode` (Dataclass)
**What it is:** A coherent narrative chunk extracted from a conversation turn by the Nemori episode segmenter.

```python
@dataclass
class Episode:
    id: str             # UUID string, auto-generated
    content: str        # The episode text (may span multiple turns)
    start_turn: int     # Index of first turn in this episode (0-indexed)
    end_turn: int       # Index of last turn in this episode (inclusive)
    session_id: str
    boundary_score: float  # 0.0–1.0. Confidence the segmenter had about this boundary.
```

**Constraints:**
- `end_turn` MUST be ≥ `start_turn`
- `boundary_score` MUST be in [0.0, 1.0]
- `content` MUST NOT be empty

---

### `ContradictionVerdict` (Dataclass)
**What it is:** The output of the Memory Court Judge Agent for a single write attempt.

```python
@dataclass
class ContradictionVerdict:
    incoming_id: str         # MemCube.id of the candidate memory
    conflicting_id: str      # MemCube.id of the existing memory that conflicts
    score: float             # 0.0 = no contradiction, 1.0 = direct conflict
    reasoning: str           # LLM explanation of why it flagged/cleared
    is_quarantined: bool     # True if score >= threshold
    suggested_resolution: Optional[str]  # LLM suggestion: "accept" | "reject" | "merge: <text>"
```

**Constraints:**
- `score` MUST be in [0.0, 1.0]
- `is_quarantined` MUST be True if and only if `score >= CONTRADICTION_THRESHOLD` (from config)
- `reasoning` MUST NOT be empty string
- `suggested_resolution` format when set: `"accept"` | `"reject"` | `"merge: <merged text>"`

---

## Validation Helpers

```python
def validate_mem_cube(cube: MemCube) -> None:
    """Raise ValueError with descriptive message for any invalid MemCube field."""
    ...

def validate_episode(episode: Episode) -> None:
    """Raise ValueError for any invalid Episode field."""
    ...
```

---

## Expected Test Outcomes (from `tests/unit/test_mem_cube.py`)

| Test | Input | Expected Output |
|---|---|---|
| MemCube auto-id | No id provided | UUID4 string assigned |
| MemCube empty content | content="" | `ValueError` raised |
| MemCube embedding length | embedding=[0.1]*100 | `ValueError` ("expected 384") |
| Provenance.new() | origin="user_input", session="abc" | version=1, parent_id=None, created_at≈now |
| bump_access | access_count=3 | new cube with access_count=4 |
| to_dict/from_dict round-trip | any valid MemCube | perfect round-trip equality |
| ContradictionVerdict score OOB | score=1.5 | `ValueError` |
| Episode end < start | start_turn=5, end_turn=3 | `ValueError` |

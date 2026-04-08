# SPEC: retrieval/ — All Retrieval Module Files

## Module Purpose
Handles all read-side memory operations. Fully stateless and read-only — never writes.
Inspired by: A-MEM (hybrid dense+symbolic), MemGPT (FIFO context pager).

---

# SPEC: retrieval/dense_retriever.py

## Purpose
Pure cosine similarity search over pgvector. No symbolic filtering.

## Class: `DenseRetriever`

```python
class DenseRetriever:
    def __init__(self, vector_client: IVectorSearch, embedder: IEmbeddingModel):
        ...
```

### `async search(query: str, top_k: int = 5, memory_types: list[MemoryType] | None = None) -> list[tuple[MemCube, float]]`

**Flow:**
1. `embedding = await embedder.embed(query)`
2. `results = await vector_client.similarity_search(embedding, top_k, memory_types)`
3. Return `results` (list of `(MemCube, cosine_score)`)

---

# SPEC: retrieval/symbolic_retriever.py

## Purpose
Tag and category-based filtering. No semantic similarity. Fast exact match.

## Class: `SymbolicRetriever`

```python
class SymbolicRetriever:
    def __init__(self, session_factory: Callable[[], AsyncSession]):
        ...
```

### `async search_by_tags(tags: list[str], top_k: int = 10) -> list[MemCube]`

**SQL:**
```sql
SELECT * FROM mem_cubes
WHERE tags @> $1::jsonb       -- Contains all specified tags
ORDER BY access_count DESC, updated_at DESC
LIMIT $2
```

**Returns:** list of MemCubes (no score — symbolic results are unranked, scored later by reranker)

### `async search_by_type(memory_type: MemoryType, session_id: str | None = None, limit: int = 20) -> list[MemCube]`
Filter by memory_type, optionally within a session.

---

# SPEC: retrieval/query_expander.py

## Purpose
A-MEM's Zettelkasten-inspired query expansion.
Before searching, expand the query using tags from linked memories.

## Class: `QueryExpander`

```python
class QueryExpander:
    def __init__(self, kg_repo: IKGRepo, symbolic_retriever: SymbolicRetriever):
        ...
```

### `async expand(query: str, seed_tags: list[str] | None = None) -> ExpandedQuery`

**What it does:**
1. If `seed_tags` provided: use them as starting point
2. Else: extract keywords from query (simple split + stopword removal)
3. Search symbolic_retriever for memories with those tags
4. Collect all unique tags from the found memories
5. Return expanded tag set for use in symbolic search

### `ExpandedQuery` (dataclass):
```python
@dataclass
class ExpandedQuery:
    original: str
    expanded_tags: list[str]   # All collected tags
    related_cube_ids: list[str] # IDs of directly related memories found during expansion
```

---

# SPEC: retrieval/reranker.py

## Purpose
Fuses dense scores + symbolic presence + recency + failure penalty into a final ranking.

## Class: `Reranker`

```python
class Reranker:
    def __init__(self, failure_reader: "ExperienceLearner", settings: Settings):
        self.dense_weight = settings.dense_weight        # default 0.7
        self.symbolic_weight = settings.symbolic_weight  # default 0.3
        self.failure_penalty = settings.failure_penalty  # default 0.4
```

### `async rerank(dense_results: list[tuple[MemCube, float]], symbolic_results: list[MemCube], query: str) -> list[RankedMemory]`

**Scoring algorithm:**
```
For each unique MemCube across both result sets:

1. dense_score  = cosine score from dense search (0.0 if not in dense results)
2. symbolic_hit = 1.0 if in symbolic results, 0.0 otherwise
3. recency_score = 1.0 / (1.0 + days_since_last_access)  # Recency boost

4. base_score = (dense_weight * dense_score) +
               (symbolic_weight * symbolic_hit)

5. failure_multiplier = failure_penalty if cube.id in known_failure_cluster else 1.0

6. final_score = base_score * recency_score * failure_multiplier
```

### `RankedMemory` (dataclass):
```python
@dataclass
class RankedMemory:
    cube: MemCube
    final_score: float
    dense_score: float
    symbolic_hit: bool
    failure_penalized: bool
    reasoning: str    # Human-readable score breakdown for UI
```

---

# SPEC: retrieval/hybrid_retriever.py

## Purpose
Orchestrates dense + symbolic + query expansion + reranking into one unified search call.
The main external interface for all retrieval. Implements `IRetriever`.

## Class: `HybridRetriever`

```python
class HybridRetriever(IRetriever):
    def __init__(
        self,
        dense: DenseRetriever,
        symbolic: SymbolicRetriever,
        expander: QueryExpander,
        reranker: Reranker,
        settings: Settings,
    ):
        ...
```

### `async search(query: str, top_k: int = 5) -> list[MemCube]`

**Full pipeline:**
```
1. expanded = await expander.expand(query)

2. dense_results = await dense.search(query, top_k=top_k * 2)  # Fetch more, reranker will prune

3. symbolic_results = await symbolic.search_by_tags(
       expanded.expanded_tags, top_k=top_k * 2
   )

4. ranked = await reranker.rerank(dense_results, symbolic_results, query)

5. Return [r.cube for r in ranked[:top_k]]
```

**Returns:** list of MemCubes sorted by final_score DESC, length = min(top_k, available results)

---

# SPEC: retrieval/context_pager.py

## Purpose
MemGPT's FIFO context window manager.
Tracks what's currently "in context" and evicts low-priority items when the token budget is exceeded.

## Class: `ContextPager`

```python
class ContextPager:
    def __init__(self, settings: Settings):
        self.budget = settings.context_window_budget   # tokens
        self._active: list[ContextSlot] = []           # Currently injected memories
```

### `ContextSlot` (dataclass):
```python
@dataclass
class ContextSlot:
    cube: MemCube
    token_count: int
    priority: float     # Higher = keep longer
    injected_at: datetime
```

### `async build_context(retrieved: list[MemCube], current_tokens_used: int) -> list[MemCube]`

**What it does:**
```
1. Estimate token count for each retrieved memory (approximate: len(content) / 4)
2. Calculate available budget: budget - current_tokens_used
3. Add retrieved memories to _active queue (ordered by priority DESC)
4. While sum(slot.token_count for slot in _active) > available_budget:
   - Evict the slot with LOWEST priority
   - Log eviction (for timeline)
5. Return [slot.cube for slot in _active]
```

### `async evict_all() -> None`
Clear the active context. Called at end of session.

### Priority calculation for a MemCube:
```python
def _priority(cube: MemCube, rerank_score: float) -> float:
    recency = 1.0 / (1.0 + (datetime.utcnow() - cube.provenance.updated_at).days)
    return 0.6 * rerank_score + 0.4 * recency
```

---

# SPEC: retrieval/experience_learner.py

## Purpose
Read-only access to failure patterns for use in reranking.
Reads from the failure log to know which memory clusters caused bad outcomes.

## Class: `ExperienceLearner`

```python
class ExperienceLearner:
    def __init__(self, failure_log: IFailureLog):
        self._cache: dict[str, int] = {}  # cube_id → failure_count
        self._cache_ttl: datetime | None = None
```

### `async get_penalized_ids() -> set[str]`

**What it does:**
1. If cache is fresh (< 60 seconds old): return from cache
2. Else: fetch `failure_log.get_patterns()` and rebuild cache
3. Return set of cube IDs that appear in failure clusters with `failure_count >= 2`

**Why threshold of 2?** A single failure might be a fluke. Two or more indicates a pattern.

---

## Unit Test Spec: tests/unit/test_hybrid_retriever.py

### Test Cases

#### `test_dense_search_returns_sorted_by_score`
- Setup: 3 MemCubes with known embeddings in mock vector client
- Query embedding: close to cube_1, far from cube_2 and cube_3
- Expected: `results[0].id == cube_1.id`

#### `test_symbolic_search_by_tags`
- Setup: Cubes with tags ["pricing", "strategy"] and ["auth", "security"]
- Query tags: ["pricing"]
- Expected: Only the pricing cube returned

#### `test_hybrid_merges_both_sources`
- Setup: Dense finds cube_A, symbolic finds cube_B (different cubes)
- Expected: Both cube_A and cube_B in final results

#### `test_reranker_penalizes_failure_clusters`
- Setup: cube_X in failure log with count=3
- Input: cube_X in dense results with score=0.9
- Expected: cube_X final_score < cube_Y final_score where cube_Y has score=0.7 but no failures

#### `test_reranker_recency_boost`
- Setup: cube_OLD (last accessed 30 days ago), cube_NEW (last accessed today), same dense score
- Expected: cube_NEW ranks higher

#### `test_context_pager_evicts_on_overflow`
- Setup: budget=100 tokens, add 3 memories × ~50 tokens each
- Expected: One evicted (lowest priority), 2 remain

#### `test_context_pager_respects_priority_order`
- Setup: 3 memories with priorities 0.9, 0.5, 0.3; budget fits only 2
- Expected: priority 0.3 evicted, 0.9 and 0.5 kept

#### `test_experience_learner_cache_freshness`
- Setup: failure_log updated after cache built
- Within 60s: returns stale cache
- After 60s: fetches fresh data

#### `test_query_expander_collects_tags`
- Setup: Memories with tags ["pricing", "B2B"] and ["B2B", "enterprise"]
- Seed: ["pricing"]
- Expected: expanded_tags includes "B2B" and "enterprise"

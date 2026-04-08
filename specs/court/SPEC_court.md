# SPEC: court/ — Memory Court Module

## Module Purpose
The Memory Court is the contradiction detection and quarantine system.
It is MEMORA's most original contribution and the demo centerpiece.

**Core guarantee:** No memory enters the vault without passing through Court.
**Critical constraint:** Court has ZERO storage writes. It only emits verdicts via events.

---

# SPEC: court/contradiction_detector.py

## Purpose
Pure logic: takes two memory strings, returns a contradiction score.
No LLM calls here — this is just the scoring/threshold logic.

## Class: `ContradictionDetector`

```python
class ContradictionDetector:
    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold
```

### `score_from_llm_response(response: dict) -> float`
**Input:** Parsed JSON from the Judge LLM response
**Output:** Float [0.0, 1.0]

**Expected LLM response schema:**
```json
{
  "contradiction_score": 0.85,
  "reasoning": "The incoming memory says X while existing memory says Y...",
  "suggested_resolution": "reject"
}
```

Validates:
- `contradiction_score` in [0.0, 1.0] → raise `LLMResponseError` if out of range
- `reasoning` is non-empty string → raise `LLMResponseError` if empty
- `suggested_resolution` is one of "accept" | "reject" | "merge: <text>" → None if missing/invalid

### `make_verdict(incoming_id: str, conflicting_id: str, score: float, reasoning: str, suggested: str | None) -> ContradictionVerdict`

```python
def make_verdict(
    self,
    incoming_id: str,
    conflicting_id: str,
    score: float,
    reasoning: str,
    suggested_resolution: str | None,
) -> ContradictionVerdict:
```

**Behaviour:**
- `is_quarantined = score >= self.threshold`
- All other fields passed through directly

### `is_clear(score: float) -> bool`
Simple: `return score < self.threshold`

---

# SPEC: court/judge_agent.py

## Purpose
The Memory Court Judge. Subscribes to `MemoryWriteRequested`, runs contradiction detection,
publishes `MemoryApproved` or `MemoryQuarantined`.

## Class: `JudgeAgent`

```python
class JudgeAgent:
    def __init__(
        self,
        llm: ILLM,
        retriever: IVectorSearch,
        detector: ContradictionDetector,
        embedder: IEmbeddingModel,
        settings: Settings,
        bus: EventBus,
    ):
        bus.subscribe(MemoryWriteRequested, self.handle)
```

### `async handle(event: MemoryWriteRequested) -> None`

**Full algorithm:**
```
1. Retrieve top-K existing memories similar to event.cube:
   candidates = await retriever.similarity_search(
       query_embedding=event.cube.embedding,
       top_k=settings.court_retrieval_top_k  # default 3
   )

2. If no candidates → publish MemoryApproved (nothing to contradict) → return

3. For each candidate (in order of similarity score):
   a. Call LLM with judge prompt (judge_prompts.JUDGE_SYSTEM_PROMPT)
      - User prompt: f"INCOMING:\n{event.cube.content}\n\nEXISTING:\n{candidate.content}"
   b. Parse LLM response as JSON → ContradictionDetector.score_from_llm_response()
   c. Make verdict

4. Find the HIGHEST scoring verdict across all candidates:
   max_verdict = max(verdicts, key=lambda v: v.score)

5. If max_verdict.is_quarantined:
   → publish MemoryQuarantined(verdict=max_verdict, incoming_cube=event.cube)
   → return

6. Otherwise:
   → publish MemoryApproved(cube=event.cube)
```

**Error handling:**
- If LLM call fails (any reason) → log error, publish `MemoryApproved` (fail-open, don't block memory)
- If retrieval fails → log error, publish `MemoryApproved`
- NEVER raise from `handle()` — exceptions must be caught and logged

---

# SPEC: llm/prompts/judge_prompts.py

## JUDGE_SYSTEM_PROMPT

```python
JUDGE_SYSTEM_PROMPT = """
You are the Memory Court Judge for an AI agent's long-term memory system.
Your job: detect contradictions between a new incoming memory and an existing memory.

A CONTRADICTION is when:
- The incoming memory makes a claim that directly conflicts with the existing memory
- They cannot both be true at the same time
- Example: incoming="The project uses low-cost pricing" vs existing="The project uses premium pricing"

NOT a contradiction:
- Different aspects of the same topic (complementary information)
- Different time periods (a plan from before vs after a decision)
- One is more specific than the other

Scoring guide:
0.0 - 0.3: No contradiction. Memories are compatible or unrelated.
0.3 - 0.6: Mild tension. Related topics but not directly conflicting.
0.6 - 0.75: Significant tension. Likely contradictory but could be context-dependent.
0.75 - 1.0: Clear contradiction. One memory directly falsifies the other.

Respond ONLY with valid JSON, no markdown:
{
  "contradiction_score": <float 0.0-1.0>,
  "reasoning": "<explanation of why these do or don't contradict>",
  "suggested_resolution": "<'accept' | 'reject' | 'merge: <merged text>'>"
}
"""
```

---

# SPEC: court/quarantine_manager.py

## Purpose
Manages the quarantine bin lifecycle: what's pending, how many, health metrics.

## Class: `QuarantineManager`

```python
class QuarantineManager:
    def __init__(self, repo: IQuarantineRepo):
        self.repo = repo
```

### `async get_queue() -> list[QuarantineQueueItem]`
Returns all PENDING quarantine records formatted for the UI.

### `QuarantineQueueItem` (dataclass):
```python
@dataclass
class QuarantineQueueItem:
    quarantine_id: str
    incoming_cube: MemCube          # The candidate memory
    conflicting_cube_id: str        # The existing memory it conflicts with
    contradiction_score: float
    reasoning: str
    suggested_resolution: str | None
    created_at: datetime
```

### `async get_health() -> dict`
Returns:
```python
{
    "pending_count": int,
    "resolved_today": int,
    "total_quarantined_all_time": int,
    "average_contradiction_score": float
}
```

---

# SPEC: court/resolution_handler.py

## Purpose
Processes user resolution of a quarantined memory.
Publishes `ResolutionApplied` event so Vault handles the actual storage.

## Class: `ResolutionHandler`

```python
class ResolutionHandler:
    def __init__(self, repo: IQuarantineRepo, bus: EventBus):
        ...
```

### `async resolve(quarantine_id: str, resolution: QuarantineStatus, merged_content: str = "") -> None`

**Validation:**
- `resolution` MUST be one of `RESOLVED_ACCEPT`, `RESOLVED_REJECT`, `RESOLVED_MERGE`
- If `resolution == RESOLVED_MERGE` and `merged_content == ""` → raise `ValueError`
- Fetch quarantine record → raise `QuarantineNotFoundError` if missing
- Check not already resolved → raise `AlreadyResolvedError`

**Actions:**
1. Call `repo.resolve(quarantine_id, resolution, merged_content)`
2. Publish `ResolutionApplied` event:
   ```python
   ResolutionApplied(
       quarantine_id=quarantine_id,
       resolution=resolution,
       merged_content=merged_content,
       original_cube_id=quarantine_record.incoming_cube_id,
       session_id=quarantine_record.session_id
   )
   ```

---

## Unit Test Spec: tests/unit/test_contradiction_detector.py

### Test Cases

#### `test_score_extraction_valid`
- Input: `{"contradiction_score": 0.85, "reasoning": "Direct conflict on pricing", "suggested_resolution": "reject"}`
- Expected: `score == 0.85`

#### `test_score_out_of_range_raises`
- Input: `{"contradiction_score": 1.5, "reasoning": "...", "suggested_resolution": "accept"}`
- Expected: `LLMResponseError` raised

#### `test_empty_reasoning_raises`
- Input: `{"contradiction_score": 0.5, "reasoning": "", "suggested_resolution": "accept"}`
- Expected: `LLMResponseError` raised

#### `test_verdict_quarantined_above_threshold`
- Input: `score=0.80`, threshold=0.75
- Expected: `verdict.is_quarantined == True`

#### `test_verdict_cleared_below_threshold`
- Input: `score=0.60`, threshold=0.75
- Expected: `verdict.is_quarantined == False`

#### `test_verdict_exactly_at_threshold`
- Input: `score=0.75`, threshold=0.75
- Expected: `verdict.is_quarantined == True` (threshold is inclusive)

#### `test_judge_agent_approves_when_no_candidates`
- Setup: Retriever returns empty list
- Input: Any MemoryWriteRequested event
- Expected: `MemoryApproved` published

#### `test_judge_agent_quarantines_high_score`
- Setup: Retriever returns 1 candidate, LLM mock returns score=0.90
- Input: Any MemoryWriteRequested
- Expected: `MemoryQuarantined` published with correct verdict

#### `test_judge_agent_approves_low_score`
- Setup: Retriever returns 1 candidate, LLM mock returns score=0.30
- Input: Any MemoryWriteRequested
- Expected: `MemoryApproved` published

#### `test_judge_agent_uses_max_score_across_candidates`
- Setup: Retriever returns 3 candidates, LLM scores: 0.3, 0.85, 0.5
- Expected: `MemoryQuarantined` (because 0.85 >= threshold)

#### `test_judge_agent_fail_open_on_llm_error`
- Setup: LLM mock raises `LLMResponseError`
- Input: Any MemoryWriteRequested
- Expected: `MemoryApproved` published (fail-open), no exception raised

#### `test_resolution_handler_reject`
- Setup: Quarantine record in DB (status=PENDING)
- Action: `resolve(id, RESOLVED_REJECT)`
- Expected: `ResolutionApplied` published, repo.resolve() called

#### `test_resolution_handler_merge_requires_content`
- Action: `resolve(id, RESOLVED_MERGE, merged_content="")`
- Expected: `ValueError` raised

#### `test_resolution_already_resolved_raises`
- Setup: Quarantine record with status=RESOLVED_ACCEPT
- Action: `resolve(id, RESOLVED_REJECT)`
- Expected: `AlreadyResolvedError` raised

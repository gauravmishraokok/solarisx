# SPEC: scheduler/ — All Scheduler Module Files

## Module Purpose
Converts raw conversation turns into typed MemCubes ready for Court evaluation.
Inspired by: Nemori (boundary detection + predict-calibrate) + MemOS (type routing).

Does NOT write to DB. Does NOT know about Court. Publishes `MemoryWriteRequested` events.

---

# SPEC: scheduler/boundary_detector.py

## Purpose
Decides if a semantic boundary exists between adjacent conversation turns.
A "boundary" means: the conversation topic shifted enough to end one episode and start another.
Inspired directly by Nemori's boundary detection mechanism.

## Class: `BoundaryDetector`

```python
class BoundaryDetector:
    def __init__(self, embedder: IEmbeddingModel, settings: Settings):
        self.embedder = embedder
        self.threshold = settings.boundary_threshold  # default 0.4
        self.buffer_size = settings.episode_buffer_size  # default 5
```

### `async score(turn_a: str, turn_b: str) -> float`
**What it does:**
1. Embed both `turn_a` and `turn_b`
2. Compute cosine similarity
3. Return `1.0 - similarity` as the "shift score" (high = topic changed)

**Output:** float in [0.0, 1.0]. 0.0 = same topic, 1.0 = completely different topic.

### `async is_boundary(turn_history: list[str], new_turn: str) -> bool`
**What it does:**
1. Compute semantic shift between `" ".join(turn_history[-3:])` and `new_turn`
2. Return True if shift score >= `self.threshold`
3. Also return True (forced boundary) if `len(turn_history) >= self.buffer_size`

**Why buffer_size matters:** Even if topics don't shift, Nemori forces a boundary after N turns to prevent episodes from growing unbounded.

---

# SPEC: scheduler/episode_segmenter.py

## Purpose
Segments a stream of conversation turns into coherent episodes using BoundaryDetector.
Each episode represents one coherent "topic" or "thought" in the conversation.

## Class: `EpisodeSegmenter`

```python
class EpisodeSegmenter:
    def __init__(self, detector: BoundaryDetector):
        self.detector = detector
        self._buffer: list[str] = []    # Current in-progress episode turns
        self._turn_index: int = 0       # Global turn counter across the session
        self._episode_start: int = 0    # Turn index where current episode started
```

### `async process_turn(turn: str, session_id: str) -> Optional[Episode]`
**What it does:**
1. Check if new turn triggers a boundary with `detector.is_boundary(self._buffer, turn)`
2. If NO boundary: append turn to buffer, return None (episode still in progress)
3. If BOUNDARY detected:
   a. Seal current buffer into an `Episode` object
   b. Reset buffer with just the new turn
   c. Update `_episode_start`
   d. Return the sealed `Episode`

**Important edge case:** First call always starts a buffer, never creates an episode (nothing to seal).

### `async flush(session_id: str) -> Optional[Episode]`
**What it does:** Force-seal whatever is in the buffer as an episode. Called at end of session.
Return None if buffer is empty.

### `Episode` output format:
```python
Episode(
    id=uuid4(),
    content=" ".join(buffer_turns),
    start_turn=self._episode_start,
    end_turn=self._turn_index - 1,
    session_id=session_id,
    boundary_score=last_boundary_score  # Score that triggered the boundary
)
```

---

# SPEC: scheduler/type_classifier.py

## Purpose
Given an Episode, decide what type of MemCube(s) to create from it.
One episode can produce MULTIPLE MemCubes (e.g. an episode about pricing might produce
one EPISODIC cube and one SEMANTIC cube for the distilled fact).

## Class: `TypeClassifier`

```python
class TypeClassifier:
    def __init__(self, llm: ILLM):
        self.llm = llm
```

### `async classify(episode: Episode) -> list[ClassificationResult]`

**What it does:**
1. Call LLM with the classifier prompt (from `llm/prompts/classifier_prompts.py`)
2. LLM returns JSON with memory type decisions
3. Return list of `ClassificationResult`

**Input to LLM:**
- System: classifier system prompt
- User: episode.content

**Expected LLM JSON response:**
```json
{
  "memories": [
    {
      "type": "episodic",
      "content": "The original episode narrative",
      "tags": ["pricing", "strategy"]
    },
    {
      "type": "semantic",
      "content": "User prefers low-cost B2B pricing model",
      "tags": ["pricing", "preference"],
      "key": "user.pricing_model_preference"
    }
  ]
}
```

**Fallback:** If LLM fails or returns unparseable JSON, create a single EPISODIC cube
with the raw episode content and `tags=[]`. Do NOT raise — log and continue.

### `ClassificationResult` (dataclass):
```python
@dataclass
class ClassificationResult:
    memory_type: MemoryType
    content: str
    tags: list[str]
    key: str | None = None   # Only for SEMANTIC type (for upsert_by_key)
```

---

# SPEC: scheduler/predict_calibrate.py

## Purpose
The Nemori predict-calibrate loop. Before accepting an episode as new knowledge,
the system first predicts what it already knows about the topic, then measures the gap.
Only the gap (new information) becomes new semantic memory.

## Class: `PredictCalibrateLoop`

```python
class PredictCalibrateLoop:
    def __init__(self, retriever: IRetriever, llm: ILLM):
        self.retriever = retriever
        self.llm = llm
```

### `async find_gap(episode: Episode, existing_memories: list[MemCube]) -> str | None`

**What it does:**
1. Ask LLM: "Given what you already know [existing_memories], what's NEW in [episode.content]?"
2. If LLM says nothing is new → return None (skip creating new semantic memory)
3. If LLM identifies a gap → return the gap description as string

**Why this matters:** Without predict-calibrate, every conversation would create duplicate
semantic memories. This is the key Nemori innovation for avoiding redundancy.

**LLM prompt structure:**
```
System: You are analyzing what new information an episode adds to an agent's knowledge base.

User:
EXISTING KNOWLEDGE:
{existing_memory_summaries}

NEW EPISODE:
{episode.content}

Identify only information in the NEW EPISODE that is NOT already covered by EXISTING KNOWLEDGE.
If everything is already known, respond with exactly: "NO_NEW_INFORMATION"
Otherwise, summarize only the genuinely new information in 1-2 sentences.
```

**Output:** `str` (the gap summary) or `None` (if "NO_NEW_INFORMATION" returned)

---

# SPEC: scheduler/ingestion_pipeline.py

## Purpose
Orchestrates the full write path. Subscribes to `ConversationTurnEvent`,
runs the full segmentation → classification → predict-calibrate chain,
then publishes `MemoryWriteRequested` for each produced MemCube.

## Class: `IngestionPipeline`

```python
class IngestionPipeline:
    def __init__(
        self,
        segmenter: EpisodeSegmenter,
        classifier: TypeClassifier,
        predict_calibrate: PredictCalibrateLoop,
        cube_factory: MemCubeFactory,
        retriever: IRetriever,
        bus: EventBus,
    ):
        bus.subscribe(ConversationTurnEvent, self.handle)
```

### `async handle(event: ConversationTurnEvent) -> None`

**Full flow:**
```
1. Combine user_message + agent_response into a single turn string:
   turn_text = f"User: {event.user_message}\nAssistant: {event.agent_response}"

2. segmenter.process_turn(turn_text, event.session_id)
   → If returns None: no episode sealed, return (nothing to process)
   → If returns Episode: continue

3. classifier.classify(episode)
   → Get list[ClassificationResult]

4. For each ClassificationResult:
   a. If type == SEMANTIC:
      - retriever.search(result.content, top_k=3)
      - predict_calibrate.find_gap(episode, retrieved)
      - If find_gap returns None: SKIP (no new info)
      - If find_gap returns gap_text: use gap_text as content
   b. If type == EPISODIC:
      - Use result.content as-is

5. For each cube to create:
   - cube_factory.create(content, type, session_id, tags=...)
   - bus.publish(MemoryWriteRequested(cube=cube, session_id=event.session_id))
```

**Error handling:**
- If classifier fails → create one EPISODIC cube from raw episode content
- If predict_calibrate fails → include the memory anyway (conservative)
- Never raise from `handle()` — log all errors

---

# SPEC: llm/prompts/segmenter_prompts.py

## Boundary Detection Prompt (not LLM — this is for the type classifier)

## CLASSIFIER_SYSTEM_PROMPT

```python
CLASSIFIER_SYSTEM_PROMPT = """
You are a memory classification assistant for an AI agent's long-term memory system.

Given a conversation episode (a coherent chunk of conversation), you must decide what memory or memories to extract from it.

Memory types:
- "episodic": A narrative memory about what happened. Includes events, discussions, decisions made. Keep temporal context.
- "semantic": A distilled fact or preference extracted from the episode. Should be timeless and reusable.

Rules:
1. Always create one "episodic" memory per episode (preserve the narrative)
2. Optionally create one or more "semantic" memories for extractable facts
3. For semantic memories, include a "key" field: a dot-notation identifier like "user.name" or "project.pricing_model"
4. Tags should be 2-5 lowercase words, no spaces

Respond ONLY with valid JSON. No markdown, no explanation.

JSON schema:
{
  "memories": [
    {
      "type": "episodic" | "semantic",
      "content": "string",
      "tags": ["string"],
      "key": "string (semantic only)"
    }
  ]
}
"""
```

---

# Integration Test Requirements (test_ingestion_pipeline.py)

## Test Cases

### `test_single_turn_no_episode`
- Input: One conversation turn, buffer_size=5
- Expected: No MemoryWriteRequested published (buffer not full, no boundary)
- Verify: `len(captured_events) == 0`

### `test_boundary_triggers_write`
- Input: 2 turns with completely different topics (embedding shift > threshold)
- Expected: At least one MemoryWriteRequested published
- Verify: `event.cube.memory_type in [EPISODIC, SEMANTIC]`

### `test_buffer_overflow_triggers_write`
- Input: 6 turns on same topic (buffer_size=5)
- Expected: One episode sealed when 6th turn arrives
- Verify: `len(captured_events) >= 1`

### `test_predict_calibrate_deduplication`
- Setup: Pre-populate vault with "User prefers low-cost B2B model"
- Input: Episode saying "User mentioned they prefer affordable pricing"
- Expected: predict_calibrate returns None, NO semantic MemoryWriteRequested published
- Verify: Only EPISODIC cube published

### `test_classifier_fallback_on_llm_error`
- Setup: LLM mock raises `LLMResponseError`
- Input: Any episode
- Expected: Falls back to one EPISODIC cube, no exception raised
- Verify: One MemoryWriteRequested published with type=EPISODIC

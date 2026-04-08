# SPEC: experience/ — Experience Module

## Module Purpose
Tracks agent failure outcomes and provides failure patterns to the retrieval module.
Implements the "Experience Learner" concept from the original architecture.

---

# SPEC: experience/failure_logger.py

## Purpose
Write-side: records failed outcomes. Implements `IFailureLog`.

## Class: `FailureLogger`

```python
class FailureLogger(IFailureLog):
    def __init__(self, session_factory: Callable[[], AsyncSession], bus: EventBus):
        bus.subscribe(NegativeOutcomeRecorded, self.handle)
```

### `async handle(event: NegativeOutcomeRecorded) -> None`
Called automatically when agent receives negative feedback.
Calls `self.log(...)` with event data.

### `async log(action: str, memory_ids: list[str], feedback: str, session_id: str) -> str`

**Inserts into `failure_log` table:**
```sql
INSERT INTO failure_log (id, session_id, action_description, memory_cluster_ids, feedback, created_at)
VALUES ($1, $2, $3, $4::jsonb, $5, NOW())
```

**Returns:** `failure_log_id`

### `async get_patterns() -> list[dict]`

**SQL:**
```sql
SELECT
    json_array_elements_text(memory_cluster_ids) AS cube_id,
    COUNT(*) AS failure_count,
    MAX(created_at) AS last_failure_at
FROM failure_log
GROUP BY cube_id
HAVING COUNT(*) >= 1
ORDER BY failure_count DESC
```

**Returns:**
```python
[
    {
        "cube_id": "abc-123",
        "failure_count": 4,
        "last_failure_at": datetime(...)
    },
    ...
]
```

---

# SPEC: experience/outcome_tracker.py

## Purpose
Links agent responses to memory clusters used in that response.
Tracks the full loop: memory retrieved → agent responded → feedback received.

## Class: `OutcomeTracker`

```python
class OutcomeTracker:
    def __init__(self):
        self._active_sessions: dict[str, ActiveSession] = {}
```

### `ActiveSession` (dataclass):
```python
@dataclass
class ActiveSession:
    session_id: str
    last_retrieved_ids: list[str]    # IDs of memories used in last agent response
    last_action: str                 # What the agent just said/did
```

### `record_retrieval(session_id: str, cube_ids: list[str], action: str) -> None`
Called after every agent response. Stores which memories were used.

### `get_active_cluster(session_id: str) -> tuple[list[str], str]`
Returns `(memory_ids, action)` for the most recent retrieval in this session.
Used when user provides feedback to know which memories to blame.

---

# SPEC: experience/pattern_matcher.py

## Purpose
Given a set of candidate MemCube IDs, determines which ones overlap with known failure patterns.

## Class: `PatternMatcher`

```python
class PatternMatcher:
    def __init__(self, failure_log: IFailureLog):
        ...
```

### `async find_overlapping_failures(candidate_ids: list[str]) -> list[FailureMatch]`

**What it does:**
1. `patterns = await failure_log.get_patterns()`
2. For each pattern, check if `pattern["cube_id"]` is in `candidate_ids`
3. Return matches

### `FailureMatch` (dataclass):
```python
@dataclass
class FailureMatch:
    cube_id: str
    failure_count: int
    last_failure_at: datetime
    penalty_multiplier: float   # settings.failure_penalty if failure_count >= 2 else 1.0
```

---

# SPEC: experience Unit Test Spec (tests/unit/test_experience_learner.py)

### Test Cases

#### `test_failure_log_write`
- Action: `log(action="agent said X", memory_ids=["id1","id2"], feedback="wrong", session_id="s1")`
- Expected: Row inserted in failure_log table

#### `test_get_patterns_aggregates_correctly`
- Setup: 3 entries in failure_log, 2 reference cube_id="cube-A", 1 references "cube-B"
- Expected: patterns includes `{"cube_id": "cube-A", "failure_count": 2}`

#### `test_pattern_matcher_overlap`
- Setup: failure_log has patterns for cube-A (count=3) and cube-C (count=1)
- Input: candidate_ids = ["cube-A", "cube-B"]
- Expected: returns FailureMatch for cube-A only

#### `test_outcome_tracker_records_and_retrieves`
- Action: record_retrieval("session-1", ["id1","id2"], "Suggested premium pricing")
- Then: get_active_cluster("session-1")
- Expected: returns (["id1","id2"], "Suggested premium pricing")

#### `test_experience_learner_threshold_penalizes_at_two`
- Setup: cube_X with failure_count=1, cube_Y with failure_count=2
- Expected: cube_X penalty_multiplier=1.0, cube_Y penalty_multiplier=settings.failure_penalty

---

# SPEC: agent/ — Agent Module

## Module Purpose
The conversational agent that uses memory to answer questions.
This is what the user actually talks to.

---

# SPEC: agent/session_manager.py

## Purpose
Manages per-session state: turn counter, context window state, session lifecycle.

## Class: `SessionManager`

```python
class SessionManager:
    def __init__(self):
        self._sessions: dict[str, SessionState] = {}
```

### `SessionState` (dataclass):
```python
@dataclass
class SessionState:
    session_id: str
    turn_count: int
    created_at: datetime
    last_active_at: datetime
    context_token_count: int   # Approximate tokens currently in context
```

### Methods:
```python
def create_session() -> str:
    """Generate new session_id, register in _sessions, return session_id."""

def get(session_id: str) -> SessionState:
    """Raise ValueError if session not found."""

def increment_turn(session_id: str) -> int:
    """Increment turn_count, update last_active_at. Return new turn_count."""

def update_token_count(session_id: str, count: int) -> None:
    """Update context_token_count for budget tracking."""
```

---

# SPEC: agent/context_builder.py

## Purpose
Assembles the system prompt for each agent call by injecting retrieved memories.

## Class: `ContextBuilder`

```python
class ContextBuilder:
    def __init__(self, context_pager: ContextPager, settings: Settings):
        ...
```

### `async build(session_id: str, retrieved: list[MemCube], base_system_prompt: str) -> str`

**What it does:**
```
1. active_memories = await context_pager.build_context(retrieved, current_token_count)

2. If no active_memories → return base_system_prompt unchanged

3. memory_block = format_memories(active_memories)

4. Return:
   f"{base_system_prompt}\n\n## RELEVANT MEMORIES\n{memory_block}"
```

### `format_memories(memories: list[MemCube]) -> str`
```
Format each memory as:
[{type}] {content}
Tags: {comma-separated tags}
Last updated: {updated_at}
---
```

---

# SPEC: agent/tool_executor.py

## Purpose
Handles LLM tool calls for explicit memory operations during a conversation.
The agent can request memory reads/writes via tool calls.

## Tools to register:

### `search_memory(query: str) -> str`
Calls `hybrid_retriever.search(query)`, returns formatted results as string.

### `store_memory(content: str, memory_type: str, tags: list[str]) -> str`
Creates a MemoryWriteRequested event directly. Returns confirmation string.
Used when agent wants to explicitly store something important mid-conversation.

### `recall_context(topic: str) -> str`
Specialized search focused on episodic memories about a topic. Returns narrative summary.

---

# SPEC: agent/memora_agent.py

## Purpose
The main agent class. Runs the turn loop. The central orchestrator.

## Class: `MemoraAgent`

```python
class MemoraAgent:
    def __init__(
        self,
        llm: ILLM,
        retriever: HybridRetriever,
        context_builder: ContextBuilder,
        tool_executor: ToolExecutor,
        session_manager: SessionManager,
        outcome_tracker: OutcomeTracker,
        bus: EventBus,
        settings: Settings,
    ):
```

### `async chat(message: str, session_id: str, feedback: str | None = None) -> AgentResponse`

**Full turn loop:**
```
1. If feedback is not None (user is giving feedback on previous response):
   a. outcome_tracker.get_active_cluster(session_id) → (memory_ids, action)
   b. If feedback is negative:
      bus.publish(NegativeOutcomeRecorded(
          action_description=action,
          memory_cluster_ids=memory_ids,
          feedback=feedback,
          session_id=session_id
      ))

2. Retrieve relevant memories:
   retrieved = await retriever.search(message, top_k=settings.top_k_retrieval)

3. Build context:
   system_prompt = await context_builder.build(
       session_id, retrieved, BASE_SYSTEM_PROMPT
   )

4. Call LLM:
   response_text = await llm.complete(system=system_prompt, user=message)

5. Record retrieval for outcome tracking:
   outcome_tracker.record_retrieval(
       session_id=session_id,
       cube_ids=[c.id for c in retrieved],
       action=response_text[:200]
   )

6. Publish ConversationTurnEvent:
   await bus.publish(ConversationTurnEvent(
       user_message=message,
       agent_response=response_text,
       turn_number=session_manager.increment_turn(session_id),
       session_id=session_id
   ))

7. Return AgentResponse
```

### `AgentResponse` (dataclass):
```python
@dataclass
class AgentResponse:
    text: str
    session_id: str
    turn_number: int
    memories_used: list[str]   # List of cube IDs used in this response
    memory_count: int          # Total memories retrieved
```

### BASE_SYSTEM_PROMPT:
```python
BASE_SYSTEM_PROMPT = """
You are MEMORA, an AI agent with persistent long-term memory.
You remember previous conversations and can reason across sessions.
When memories are provided, use them to give consistent, contextually aware answers.
If your memories contain contradictory information, acknowledge the contradiction honestly.
"""
```

---

# SPEC: llm/ — LLM Module

## Module Purpose
LLM provider abstraction. Only module allowed to make external API calls.

---

# SPEC: llm/base.py

Abstract `ILLM` class (already specified in `core/interfaces.py`).
This file re-exports it for convenience: `from memora.llm.base import ILLM`.

---

# SPEC: llm/claude_client.py

## Class: `ClaudeClient`

```python
class ClaudeClient(ILLM):
    def __init__(self, api_key: str, model: str = "claude-opus-4-5"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
```

### `async complete(system: str, user: str, max_tokens: int = 1000) -> str`
- Call `client.messages.create()`
- Return `response.content[0].text`
- On 429 → raise `LLMRateLimitError`
- On other API error → raise `LLMResponseError`

### `async complete_json(system: str, user: str, schema: dict, max_tokens: int = 1000) -> dict`
- Append to system: `"\n\nYou MUST respond with valid JSON only. No markdown, no explanation."`
- Call `complete()`
- Strip any markdown code fences (```json ... ```)
- Parse JSON → raise `LLMResponseError` if unparseable
- Validate against schema (basic key presence check) → raise `LLMResponseError` if missing required keys
- Return dict

### Retry logic:
- Retry up to 3 times on `LLMRateLimitError` with exponential backoff: 1s, 2s, 4s

---

# SPEC: llm/openai_client.py

## Class: `OpenAIClient`
Identical interface to `ClaudeClient`. Uses `openai.AsyncOpenAI`.
Fallback provider. Model: `gpt-4o-mini` default.

---

# Integration Test Spec: tests/integration/test_agent_conversation.py

### Test Cases

#### `test_agent_responds_to_message`
- Setup: Fresh session, all real components (test DB), mock LLM
- Input: `chat("What is our pricing strategy?", session_id)`
- Expected: Response text non-empty, `turn_number == 1`

#### `test_agent_injects_memories_in_context`
- Setup: Pre-populate vault with "Pricing: low-cost B2B"
- Input: `chat("What pricing approach do I use?", session_id)`
- Expected: LLM was called with system_prompt containing "low-cost B2B"
  (verify by inspecting mock LLM's captured `system` argument)

#### `test_agent_publishes_conversation_turn_event`
- Setup: Event listener on `ConversationTurnEvent`
- Action: `chat("hello", session_id)`
- Expected: `ConversationTurnEvent` published with correct session_id

#### `test_negative_feedback_triggers_failure_log`
- Setup: Two-turn conversation
- Turn 1: `chat("What approach?", session_id)` → records retrieval
- Turn 2: `chat("next question", session_id, feedback="That was wrong")`
- Expected: `NegativeOutcomeRecorded` published → `FailureLog` entry created

#### `test_session_manager_tracks_turns`
- Input: 3 sequential `chat()` calls on same session
- Expected: `turn_number` in response is 1, 2, 3 respectively

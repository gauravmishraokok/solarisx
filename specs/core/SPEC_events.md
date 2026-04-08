# SPEC: core/events.py

## Purpose
The event bus and all typed event dataclasses. This is the **only** channel through which modules
communicate side effects to each other. No module should import another module's internals to trigger
behaviour — it must publish an event instead.

## File Location
`memora/core/events.py`

## Dependencies
- `memora.core.types` (MemCube, ContradictionVerdict, QuarantineStatus)
- Python stdlib: `dataclasses`, `typing`, `datetime`

---

## EventBus Class

### Purpose
A simple synchronous publish/subscribe bus. Hackathon version is in-process.
Upgrade path: swap internal dispatch to `asyncio.Queue` or Redis Streams without changing any subscriber code.

### Implementation

```python
class EventBus:
    def __init__(self):
        self._handlers: dict[Type[BaseEvent], list[Callable[[BaseEvent], Awaitable[None]]]] = {}

    def subscribe(self, event_type: Type[BaseEvent], handler: Callable) -> None:
        """Register a handler for an event type. Multiple handlers allowed per type."""
        ...

    async def publish(self, event: BaseEvent) -> None:
        """
        Call all registered handlers for this event type.
        Handlers are called sequentially (order = registration order).
        If a handler raises, log the error but continue calling remaining handlers.
        MUST NOT raise an exception to the caller even if handlers fail.
        """
        ...

    def clear(self) -> None:
        """Remove all handlers. Used in tests to reset state between test cases."""
        ...
```

**Constraints:**
- `publish` MUST be `async`
- Handlers MUST be called in registration order
- Handler failures MUST be logged but MUST NOT propagate to publisher
- `clear()` MUST remove ALL subscriptions (critical for test isolation)

### Module-level singleton
```python
bus = EventBus()
```
All modules import and use this singleton. Tests call `bus.clear()` in their teardown.

---

## BaseEvent

```python
@dataclass
class BaseEvent:
    timestamp: datetime    # UTC, auto-set
    session_id: str        # Links event to a conversation session
```

All events inherit from BaseEvent.

---

## Event Catalogue

### `ConversationTurnEvent`
**Publisher:** `agent/memora_agent.py`
**Subscribers:** `scheduler/ingestion_pipeline.py`
**When:** After every complete agent turn (user message + agent response both available)

```python
@dataclass
class ConversationTurnEvent(BaseEvent):
    user_message: str    # Raw user message text
    agent_response: str  # Agent's reply text
    turn_number: int     # 0-indexed within session
```

---

### `MemoryWriteRequested`
**Publisher:** `scheduler/ingestion_pipeline.py`
**Subscribers:** `court/judge_agent.py`
**When:** Scheduler has produced a new MemCube candidate that needs Court approval

```python
@dataclass
class MemoryWriteRequested(BaseEvent):
    cube: MemCube   # The candidate MemCube (not yet in any DB)
```

**Note:** `cube.id` is already assigned. If Court rejects, this ID is abandoned.

---

### `MemoryApproved`
**Publisher:** `court/judge_agent.py`
**Subscribers:** `vault/` (via `api/dependencies.py` wiring)
**When:** Court judge scored contradiction < threshold

```python
@dataclass
class MemoryApproved(BaseEvent):
    cube: MemCube   # Approved MemCube, ready to write to vault
```

---

### `MemoryQuarantined`
**Publisher:** `court/judge_agent.py`
**Subscribers:** `vault/quarantine_repo.py` (via wiring)
**When:** Court judge scored contradiction >= threshold

```python
@dataclass
class MemoryQuarantined(BaseEvent):
    verdict: ContradictionVerdict
    incoming_cube: MemCube      # The candidate that was flagged
```

---

### `ResolutionApplied`
**Publisher:** `court/resolution_handler.py`
**Subscribers:** `vault/` (via wiring)
**When:** User has resolved a quarantined memory via the UI

```python
@dataclass
class ResolutionApplied(BaseEvent):
    quarantine_id: str
    resolution: QuarantineStatus   # One of the RESOLVED_* values
    merged_content: str            # Only meaningful for RESOLVED_MERGE; empty string otherwise
    original_cube_id: str          # The incoming cube's ID
```

---

### `NegativeOutcomeRecorded`
**Publisher:** `agent/memora_agent.py` (when user signals bad answer)
**Subscribers:** `experience/failure_logger.py`
**When:** User provides negative feedback on an agent response

```python
@dataclass
class NegativeOutcomeRecorded(BaseEvent):
    action_description: str        # What the agent did
    memory_cluster_ids: list[str]  # IDs of MemCubes that were active in context
    feedback: str                  # User's negative feedback text
```

---

## Wiring Contract

The `api/app.py` lifespan function is responsible for wiring all subscriptions:

```python
# In api/app.py lifespan:
bus.subscribe(ConversationTurnEvent, ingestion_pipeline.handle)
bus.subscribe(MemoryWriteRequested,  judge_agent.handle)
bus.subscribe(MemoryApproved,        vault_writer.handle_approved)
bus.subscribe(MemoryQuarantined,     vault_writer.handle_quarantined)
bus.subscribe(ResolutionApplied,     vault_writer.handle_resolution)
bus.subscribe(NegativeOutcomeRecorded, failure_logger.handle)
```

No module self-registers in `__init__`. Registration only happens in `api/app.py`. This makes the wiring explicit, testable, and not side-effectful on import.

---

## Expected Test Outcomes

| Test | Scenario | Expected |
|---|---|---|
| subscribe + publish | Handler registered, event published | Handler called once with correct event |
| multiple handlers | 2 handlers for same type | Both called in registration order |
| handler error | Handler raises RuntimeError | Other handlers still called; publish doesn't raise |
| wrong event type | Handler for TypeA, publish TypeB | Handler NOT called |
| clear() isolation | Register handler, clear(), publish | Handler NOT called |
| async handler | Async handler registered | Awaited correctly, no warning |
| session_id propagation | Event published with session_id="abc" | Handler receives event.session_id=="abc" |

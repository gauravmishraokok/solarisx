# SPEC: scripts/ + Master Integration Contract

---

# SPEC: scripts/seed_demo_data.py

## Purpose
Populates the database with rich demo data so the presentation starts with a populated
knowledge graph and one pre-seeded contradiction ready to demonstrate.

## Usage
```bash
make seed
# or
poetry run python scripts/seed_demo_data.py
```

## Implementation

```python
import asyncio
from memora.core.config import get_settings
from memora.core.types import MemoryType
from memora.vault.mem_cube import MemCubeFactory
from memora.storage.vector.embedding import SentenceTransformerEmbedder
# ... other imports

async def main():
    settings = get_settings()
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    factory = MemCubeFactory(embedder, settings)

    # Create DB session
    # Insert demo memories directly (bypass Court for seeding)
    # Insert pre-seeded quarantine record

    print("✅ Demo data seeded successfully")
    print(f"  Episodic memories: {episodic_count}")
    print(f"  Semantic memories: {semantic_count}")
    print(f"  KG nodes: {kg_count}")
    print(f"  Quarantine records: 1 (pending contradiction for demo)")

asyncio.run(main())
```

**Expected console output:**
```
✅ Demo data seeded successfully
  Episodic memories: 8
  Semantic memories: 6
  KG nodes: 4
  KG edges: 6
  Quarantine records: 1 (pending contradiction for demo)
```

---

# SPEC: scripts/run_locomo_eval.py

## Purpose
Run the LoCoMo conversational memory benchmark against MEMORA.
Used to validate that the memory system improves QA accuracy vs no-memory baseline.

## Expected usage:
```bash
poetry run python scripts/run_locomo_eval.py --num-samples 50 --output results.json
```

## Implementation outline:
```python
"""
LoCoMo eval: loads multi-turn conversations from LoCoMo dataset,
runs them through MEMORA agent, compares answers to gold labels.

Metrics reported:
- Exact match accuracy
- F1 score
- Sessions with memory retrieval (% that actually used memory)
"""

async def run_evaluation(num_samples: int) -> dict:
    results = {
        "total": num_samples,
        "exact_match": 0,
        "f1": 0.0,
        "memory_used_pct": 0.0,
    }
    # For each sample:
    #   1. Create fresh session
    #   2. Feed all turns through agent.chat()
    #   3. Ask evaluation question
    #   4. Compare to gold answer
    return results
```

---

# SPEC: scripts/export_graph.py

## Purpose
Export the knowledge graph to a JSON file for offline visualization or debugging.

## Expected output JSON format:
```json
{
  "exported_at": "2025-01-01T10:30:00Z",
  "node_count": 12,
  "edge_count": 18,
  "nodes": [
    {"id": "abc", "content": "...", "type": "kg_node", "tier": "warm", "tags": [...]}
  ],
  "edges": [
    {"id": "def", "from": "abc", "to": "xyz", "label": "relates_to", "active": true}
  ]
}
```

---

# MASTER INTEGRATION CONTRACT

## The Full Request Lifecycle

This is what happens when a user types "We should switch to premium pricing" in the chat:

```
1. POST /chat
   {message: "We should switch to premium pricing", session_id: "s1"}

2. api/routers/chat.py → agent.chat(message, session_id)

3. agent/memora_agent.py:
   a. retriever.search("We should switch to premium pricing", top_k=5)
      → HybridRetriever: embed query → pgvector search → tag search → rerank
      → Returns: [MemCube("pricing model: freemium $29/month"), ...]

   b. context_builder.build(session_id, retrieved, BASE_SYSTEM_PROMPT)
      → context_pager.build_context(retrieved, current_tokens)
      → Returns: system_prompt with memory block injected

   c. llm.complete(system=system_prompt, user=message)
      → Returns: agent response text

   d. outcome_tracker.record_retrieval(session_id, [cube_ids], response[:200])

   e. bus.publish(ConversationTurnEvent(
          user_message=message,
          agent_response=response,
          turn_number=2,
          session_id="s1"
      ))

4. scheduler/ingestion_pipeline.py receives ConversationTurnEvent:
   a. segmenter.process_turn(turn_text, "s1")
      → BoundaryDetector checks semantic shift
      → If boundary: returns Episode("pricing discussion", start=1, end=1)

   b. classifier.classify(episode)
      → LLM returns: [{type: "episodic", content: ...}, {type: "semantic", content: "User wants premium pricing", key: "product.pricing_model"}]

   c. For semantic: predict_calibrate.find_gap(episode, retrieved_similar)
      → LLM says: gap = "User now prefers premium over freemium"

   d. cube_factory.create("User now prefers premium...", SEMANTIC, "s1", tags=["pricing"])
      → New MemCube with embedding

   e. bus.publish(MemoryWriteRequested(cube=new_cube, session_id="s1"))

5. court/judge_agent.py receives MemoryWriteRequested:
   a. similarity_search(new_cube.embedding, top_k=3)
      → Returns: [MemCube("pricing model: freemium $29/month", score=0.89)]

   b. For each candidate: llm.complete_json(judge_prompt, f"INCOMING: {new}  EXISTING: {existing}")
      → Returns: {contradiction_score: 0.88, reasoning: "...", suggested_resolution: "reject"}

   c. max_verdict = {score: 0.88, is_quarantined: True}

   d. bus.publish(MemoryQuarantined(verdict=max_verdict, incoming_cube=new_cube))

6. vault/VaultEventWriter receives MemoryQuarantined:
   quarantine_repo.save_pending(new_cube, verdict)
   → QuarantineRecord created with status=PENDING

7. Frontend polls GET /court/queue every 3s
   → Gets: [{quarantine_id: "q1", incoming: "User wants premium...",
             conflicting: "pricing model: freemium $29/month",
             score: 0.88}]

8. Court panel lights up. User clicks "Accept".

9. POST /court/resolve/q1 {resolution: "accept"}
   → api/routers/court.py → resolution_handler.resolve("q1", RESOLVED_ACCEPT)
   → quarantine_repo.resolve("q1", RESOLVED_ACCEPT)
   → bus.publish(ResolutionApplied(quarantine_id="q1", resolution=RESOLVED_ACCEPT, original_cube_id=...))

10. vault/VaultEventWriter receives ResolutionApplied:
    → episodic_repo.save(new_cube)  (the original MemCube, now approved)
    → timeline: event_type="resolved"

11. KG updated. Graph panel shows new node. Timeline shows new event.
    Health panel: total_memories + 1.
```

---

## Pass Criteria for Each Module

### Core (always passes if spec followed)
- [ ] `MemCube` creates with UUID if no ID
- [ ] `Provenance` version starts at 1
- [ ] `EventBus.publish` catches handler errors
- [ ] `Settings` validates threshold bounds

### Storage (requires Docker)
- [ ] pgvector similarity search returns sorted results
- [ ] quarantine round-trip: save → list → resolve
- [ ] timeline events written on every vault operation

### Vault
- [ ] `MemCubeFactory.create` never returns cube with empty embedding
- [ ] `TierRouter` follows the access_count + days decision table
- [ ] `SemanticRepo.upsert_by_key` creates version chain

### Scheduler
- [ ] Buffer overflow forces episode boundary at episode_buffer_size
- [ ] `predict_calibrate` returns None when no new info (deduplication)
- [ ] Classifier fallback produces EPISODIC cube on LLM failure

### Court
- [ ] Judge publishes `MemoryApproved` when no similar memories exist
- [ ] Judge publishes `MemoryQuarantined` when max score >= threshold
- [ ] Resolution handler raises `AlreadyResolvedError` on double resolve
- [ ] `RESOLVED_MERGE` requires non-empty merged_content

### Retrieval
- [ ] `HybridRetriever` returns cubes sorted by final_score DESC
- [ ] `Reranker` penalizes cubes in failure log (failure_count >= 2)
- [ ] `ContextPager` evicts lowest-priority when over budget

### Experience
- [ ] `FailureLogger` subscribes to `NegativeOutcomeRecorded`
- [ ] `ExperienceLearner` cache refreshes after 60s

### Agent
- [ ] `MemoraAgent.chat` publishes `ConversationTurnEvent` on every turn
- [ ] Negative feedback triggers `NegativeOutcomeRecorded`
- [ ] `turn_number` increments per session

### API
- [ ] All 5 routers registered and reachable
- [ ] 404 on missing memory/quarantine
- [ ] 409 on double resolve
- [ ] CORS allows `localhost:5173`

### End-to-End
- [ ] Full demo scenario: 5-step flow completes without error
- [ ] Court queue populated after contradiction → queue empty after resolve
- [ ] Graph has nodes after conversation

# MEMORA
### Persistent Memory for Long-Running AI Agents

> *"Most AI systems today are brilliant — and amnesiac. MEMORA fixes the second part."*

---

## The Problem

Every time you start a new conversation with an AI agent, it forgets everything. You re-explain your preferences. It contradicts what it told you last week. It makes the same mistake it made yesterday. This is the **Amnesia Problem** — and it's not a bug, it's a fundamental architectural gap.

The issue isn't just *no* memory. It's that memory, when it exists at all, is:
- **Flat** — no distinction between a passing comment and a core fact
- **Unvalidated** — contradictory beliefs can coexist silently
- **Unmanaged** — stale information is never evicted or updated
- **Unlearned** — failures don't inform future behaviour

**Memory is not storage. It's a system.** It needs structure, lifecycle, validation, and evolution. That's what MEMORA is.

---

## What We Built

MEMORA is an event-driven, tiered memory operating system for AI agents — inspired by four research systems ([MemGPT](https://github.com/cpacker/MemGPT), [MemOS](https://github.com/MemTensor/MemOS), [Nemori](https://github.com/Shichun-Liu/Agent-Memory-Paper-List), [A-MEM](https://github.com/agiresearch/A-mem)) and extended with two original contributions: the **Memory Court** and the **Experience Learner**.

```
User Message → Agent → Retriever → Context Builder → LLM → Response
                 ↓
         ConversationTurnEvent
                 ↓
        Ingestion Pipeline (Nemori)
                 ↓
         MemoryWriteRequested
                 ↓
        Memory Court / Judge (original)
           ↙              ↘
   MemoryApproved    MemoryQuarantined
           ↓                  ↓
      Vault (MemOS)     Human Resolution
           ↓
   Experience Learner (original)
```

---

## The Architecture — Layer by Layer

### Layer 1 — MemCube (The Memory Unit)
*Inspired by MemOS*

Every piece of information in MEMORA is a `MemCube` — a typed, versioned, provenanced memory object. Not a string. Not a vector. A first-class domain object.

```python
@dataclass
class MemCube:
    id: str                        # UUID
    content: str                   # The actual memory text
    memory_type: MemoryType        # EPISODIC | SEMANTIC | KG_NODE
    tier: MemoryTier               # HOT | WARM | COLD
    tags: list[str]
    embedding: list[float]         # 384-dim (all-MiniLM-L6-v2)
    provenance: Provenance         # Origin, version chain, timestamps
    access_count: int
    ttl_seconds: Optional[int]
```

Three memory types, each serving a distinct cognitive role:
- **EPISODIC** — *"On Tuesday we discussed pricing strategy"* — narrative with temporal context
- **SEMANTIC** — *"User prefers low-cost B2B model"* — distilled, timeless facts
- **KG_NODE** — entities in the knowledge graph with versioned relationships

---

### Layer 2 — Tiered Storage (HOT / WARM / COLD)
*Inspired by MemGPT's OS memory model*

Not all memories are equally important. MEMORA routes each MemCube to the right tier automatically:

```python
def decide(self, cube: MemCube) -> MemoryTier:
    if cube.access_count >= 10 and last_access_within(cube, hours=24):
        return MemoryTier.HOT    # In-memory / KV-cache
    elif cube.access_count >= 1 or created_within(cube, days=7):
        return MemoryTier.WARM   # Active pgvector store
    else:
        return MemoryTier.COLD   # Archived
```

The `TTLManager` runs periodic cycles to promote hot memories and evict expired ones — keeping the system lean for long-running agents.

---

### Layer 3 — Episode Segmentation + Predict-Calibrate
*Inspired by Nemori*

Raw conversation turns don't map cleanly to memories. MEMORA segments them into coherent **episodes** using semantic boundary detection:

```python
async def is_boundary(self, history: list[str], new_turn: str) -> bool:
    shift_score = 1.0 - cosine_similarity(
        await self.embedder.embed(" ".join(history[-3:])),
        await self.embedder.embed(new_turn)
    )
    return shift_score >= self.threshold or len(history) >= self.buffer_size
```

Before any episode becomes a new semantic memory, the **Predict-Calibrate loop** checks if we already know it:

```
LLM: "Given what you already know, what's NEW in this episode?"
→ "NO_NEW_INFORMATION" → skip (no duplicate semantic memory created)
→ "User now prefers X over Y" → create new semantic cube
```

This eliminates redundant memory creation — a core Nemori innovation.

---

### Layer 4 — Hybrid Retrieval
*Inspired by A-MEM's Zettelkasten approach*

Every retrieval call combines three signals:

```python
async def search(self, query: str, top_k: int = 5) -> list[MemCube]:
    expanded = await self.expander.expand(query)          # Tag expansion via KG
    dense    = await self.dense.search(query, top_k*2)    # Cosine similarity
    symbolic = await self.symbolic.search(expanded.tags)  # Exact tag match
    ranked   = await self.reranker.rerank(dense, symbolic, query)
    return [r.cube for r in ranked[:top_k]]
```

The **Reranker** fuses four factors into a final score:
```
final_score = (0.7 × dense_score + 0.3 × symbolic_hit)
            × recency_decay
            × failure_penalty  ← our original contribution
```

---

### Layer 5 — Memory Court ⚖️
*Original contribution — no equivalent in any paper*

Before any memory is written to the vault, it passes through the **Memory Court** — an LLM-powered contradiction detector.

```python
async def _on_write_requested(self, event: MemoryWriteRequested):
    candidates = await self.retriever.search(event.cube.content, top_k=3)
    
    verdicts = []
    for candidate in candidates:
        response = await self.llm.complete_json(
            system=JUDGE_SYSTEM_PROMPT,
            user=f"INCOMING:\n{event.cube.content}\n\nEXISTING:\n{candidate.content}"
        )
        verdicts.append(self.detector.make_verdict(..., score=response["contradiction_score"]))
    
    max_verdict = max(verdicts, key=lambda v: v.score)
    
    if max_verdict.score >= self.threshold:   # default: 0.75
        await bus.publish(MemoryQuarantined(verdict=max_verdict, incoming_cube=event.cube))
    else:
        await bus.publish(MemoryApproved(cube=event.cube))
```

**Critical design invariant: Court never writes to DB. It only emits verdicts.**

Contradictions go to the **Quarantine Bin** — a pending queue where humans resolve them: Accept / Reject / Merge. The resolution feeds back through the event bus to the vault.

```
INCOMING: "We should pivot to premium enterprise pricing"
EXISTING: "Pricing model: freemium with $29/month pro tier"
SCORE: 0.88 → QUARANTINED
REASONING: "Direct conflict on pricing strategy..."
SUGGESTED: "reject"
```

---

### Layer 6 — Experience Learner 🧠
*Original contribution — closes the failure feedback loop*

When a user tells the agent its response was wrong, MEMORA doesn't just log it — it learns which memories caused the failure:

```python
# Turn 1: Agent answers using memories [cube-A, cube-B]
outcome_tracker.record_retrieval(session_id, ["cube-A", "cube-B"], response)

# Turn 2: User says "That was wrong"
bus.publish(NegativeOutcomeRecorded(
    memory_cluster_ids=["cube-A", "cube-B"],
    feedback="That recommendation was completely off"
))

# Future retrieval: cube-A now has failure_count=2
# Reranker applies penalty: final_score × 0.4
# cube-A ranked lower → less likely to cause the same mistake again
```

The penalty threshold is 2 failures — one failure might be a fluke, two is a pattern.

---

### Layer 7 — Event Bus (The Glue)

All cross-module communication flows through a typed event bus. No module imports another module's internals for side effects.

```python
# The full write path — no module knows about any other
bus.subscribe(ConversationTurnEvent,   ingestion_pipeline.handle)
bus.subscribe(MemoryWriteRequested,    judge_agent.handle)
bus.subscribe(MemoryApproved,          vault_writer.handle_approved)
bus.subscribe(MemoryQuarantined,       vault_writer.handle_quarantined)
bus.subscribe(ResolutionApplied,       vault_writer.handle_resolution)
bus.subscribe(NegativeOutcomeRecorded, failure_logger.handle)
```

This means every module is independently testable. 105 tests pass with zero real DB calls in unit tests.

---

## The Demo Scenario

```
1. "We're building a low-cost B2B product targeting SMBs."
   → Memory stored: [SEMANTIC] pricing.model = "low-cost B2B"

2. "Let's shift to a premium enterprise pricing strategy."
   → Memory Court fires. Score: 0.88. QUARANTINED.
   → UI: Contradiction card appears with [Accept] [Reject] [Merge]

3. User clicks "Accept"
   → ResolutionApplied event → memory written to vault
   → Knowledge graph updates live

4. "What approach failed last time we tried premium?"
   → Experience Learner surfaces failure log
   → Reranker penalizes premium-related memories
```

---

## Running MEMORA

### Prerequisites
```bash
docker-compose up -d          # PostgreSQL + pgvector + Neo4j
cp .env.example .env          # Add your GROQ_API_KEY
poetry install
```

### Start
```bash
make migrate                  # Run Alembic migrations
make seed                     # Load demo data (8 memories + 1 pre-seeded contradiction)
make dev                      # Backend on :8000
make frontend                 # React dashboard on :5173
```

### Test
```bash
make test-unit                # 88 tests, no Docker needed, ~1.4s
make test-integration         # Requires docker-compose up
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Groq API / Llama3-70b |
| Embeddings | `all-MiniLM-L6-v2` (384-dim) |
| Vector Search | PostgreSQL + pgvector |
| Graph | Neo4j (prod) / NetworkX (demo) |
| Backend | FastAPI + SQLAlchemy async |
| Frontend | React + D3.js + Tailwind |
| Tests | pytest + pytest-asyncio (strict mode) |

---

## Test Coverage

```
105 tests · 0 failures · 0 warnings

Unit:        71 tests  (no Docker, ~0.8s)
Integration: 34 tests  (mocked infrastructure)
E2E:          —        (requires live stack, run on demo day)
```

---

## Team

| Person | Modules | Key Contribution |
|---|---|---|
| **Gaurab Mishra** | `core/`, `storage/`, `vault/` | Domain types, pgvector storage, MemCube factory, three-tier routing, provenance system |
| **Arnav Singh* | `scheduler/`, `llm/`, `retrieval/` | Nemori episode segmentation, predict-calibrate deduplication, hybrid dense+symbolic retrieval, Groq integration |
| **Avinash Pal** | `court/`, `experience/`, `agent/` | Memory Court contradiction detector, Experience Learner failure loop, MemoraAgent conversation orchestrator |
| **Lavish** | `api/`, `frontend/` | FastAPI wiring, React dashboard, D3 knowledge graph, Court UI, timeline panel |

---

## What Makes This Different

| Feature | Standard RAG | MEMORA |
|---|---|---|
| Memory type | Flat chunks | EPISODIC + SEMANTIC + KG |
| Write validation | None | Memory Court (LLM contradiction check) |
| Retrieval | Dense only | Dense + symbolic + KG expansion |
| Failure learning | None | Experience Learner with penalty scoring |
| Tier management | None | HOT / WARM / COLD with auto-promotion |
| Contradictions | Silent | Quarantine → human resolution |
| Architecture | Monolithic | Event-driven, fully decoupled |

---

## Paper Attribution

| Concept | Source Paper | Where We Use It |
|---|---|---|
| Hierarchical memory tiers | MemGPT (Packer et al., 2023) | `vault/tier_router.py`, `retrieval/context_pager.py` |
| MemCube + provenance | MemOS (MemTensor, 2025) | `vault/mem_cube.py`, `vault/provenance.py` |
| Episode boundary detection | Nemori (2025) | `scheduler/episode_segmenter.py` |
| Predict-calibrate loop | Nemori (2025) | `scheduler/predict_calibrate.py` |
| Zettelkasten linking | A-MEM (Xu et al., 2025) | `retrieval/query_expander.py`, `vault/kg_repo.py` |
| Hybrid dense+symbolic | A-MEM (Xu et al., 2025) | `retrieval/hybrid_retriever.py` |
| **Memory Court** | **Original** | `court/` |
| **Experience Learner** | **Original** | `experience/`, `retrieval/reranker.py` |

---

*Built for the SolarisX Hackathon — April 2026*
# SPEC: api/ — FastAPI Layer

## Module Purpose
Thin HTTP wrapper. Zero business logic lives here.
Translates HTTP requests → service calls → HTTP responses.

---

# SPEC: api/app.py

## Purpose
FastAPI application factory with lifespan for startup/shutdown wiring.

## Function: `create_app() -> FastAPI`

```python
def create_app() -> FastAPI:
    app = FastAPI(
        title="MEMORA",
        description="Persistent Memory for Long-Running Agents",
        version="0.1.0",
    )
    # Add middleware
    # Register routers
    # Setup lifespan
    return app
```

## Lifespan: `@asynccontextmanager async def lifespan(app: FastAPI)`

**On startup:**
```python
# 1. Load settings
settings = get_settings()

# 2. Create DB engine + run migrations
engine = await create_engine(settings.database_url)

# 3. Initialize embedding model
embedder = SentenceTransformerEmbedder(settings.embedding_model)

# 4. Initialize storage clients
pg_client = PgVectorClient(session_factory)
graph_client = NetworkXClient() if settings.use_networkx_fallback else Neo4jClient(...)

# 5. Initialize vault
cube_factory = MemCubeFactory(embedder, settings)
episodic_repo = EpisodicRepo(pg_client, timeline_writer)
kg_repo = KGRepo(graph_client, timeline_writer)
quarantine_repo = QuarantineRepo(session_factory)

# 6. Initialize retrieval
dense = DenseRetriever(pg_client, embedder)
symbolic = SymbolicRetriever(session_factory)
expander = QueryExpander(kg_repo, symbolic)
failure_log = FailureLogger(session_factory, bus)
experience_learner = ExperienceLearner(failure_log)
reranker = Reranker(experience_learner, settings)
retriever = HybridRetriever(dense, symbolic, expander, reranker, settings)
context_pager = ContextPager(settings)

# 7. Initialize LLM
llm = ClaudeClient(settings.anthropic_api_key, settings.llm_model)

# 8. Initialize court
detector = ContradictionDetector(settings.contradiction_threshold)
judge = JudgeAgent(llm, pg_client, detector, embedder, settings, bus)
quarantine_mgr = QuarantineManager(quarantine_repo)
resolution_handler = ResolutionHandler(quarantine_repo, bus)

# 9. Initialize scheduler
boundary_detector = BoundaryDetector(embedder, settings)
segmenter = EpisodeSegmenter(boundary_detector)
classifier = TypeClassifier(llm)
predict_calibrate = PredictCalibrateLoop(retriever, llm)
pipeline = IngestionPipeline(segmenter, classifier, predict_calibrate,
                             cube_factory, retriever, bus)

# 10. Initialize agent
session_mgr = SessionManager()
context_builder = ContextBuilder(context_pager, settings)
outcome_tracker = OutcomeTracker()
tool_executor = ToolExecutor(retriever, cube_factory, bus)
agent = MemoraAgent(llm, retriever, context_builder, tool_executor,
                    session_mgr, outcome_tracker, bus, settings)

# 11. Wire vault event handlers
vault_writer = VaultEventWriter(episodic_repo, semantic_repo, kg_repo,
                                quarantine_repo, cube_factory)
bus.subscribe(MemoryApproved, vault_writer.handle_approved)
bus.subscribe(MemoryQuarantined, vault_writer.handle_quarantined)
bus.subscribe(ResolutionApplied, vault_writer.handle_resolution)
bus.subscribe(NegativeOutcomeRecorded, failure_log.handle)

# 12. Store all services in app.state for dependency injection
app.state.agent = agent
app.state.retriever = retriever
app.state.quarantine_mgr = quarantine_mgr
app.state.resolution_handler = resolution_handler
app.state.episodic_repo = episodic_repo
app.state.kg_repo = kg_repo
app.state.settings = settings
```

**On shutdown:**
```python
await context_pager.evict_all()
await dispose_engine()
bus.clear()
```

---

# SPEC: api/dependencies.py

## Purpose
FastAPI dependency injection helpers. Extract services from `app.state`.

```python
def get_agent(request: Request) -> MemoraAgent:
    return request.app.state.agent

def get_quarantine_manager(request: Request) -> QuarantineManager:
    return request.app.state.quarantine_mgr

def get_resolution_handler(request: Request) -> ResolutionHandler:
    return request.app.state.resolution_handler

def get_episodic_repo(request: Request) -> IEpisodicRepo:
    return request.app.state.episodic_repo

def get_kg_repo(request: Request) -> IKGRepo:
    return request.app.state.kg_repo

def get_settings(request: Request) -> Settings:
    return request.app.state.settings
```

---

# SPEC: api/schemas/

## chat_schemas.py

```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = None    # If None, agent creates new session
    feedback: str | None = None      # Feedback on previous response (positive/negative)

class ChatResponse(BaseModel):
    text: str
    session_id: str
    turn_number: int
    memories_used: list[str]   # Cube IDs
    memory_count: int
```

## memory_schemas.py

```python
class MemoryCubeResponse(BaseModel):
    id: str
    content: str
    memory_type: str
    tier: str
    tags: list[str]
    access_count: int
    created_at: str
    updated_at: str

class MemoryListResponse(BaseModel):
    memories: list[MemoryCubeResponse]
    total: int

class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    memory_types: list[str] | None = None
```

## court_schemas.py

```python
class QuarantineItemResponse(BaseModel):
    quarantine_id: str
    incoming_content: str
    conflicting_cube_id: str
    contradiction_score: float
    reasoning: str
    suggested_resolution: str | None
    created_at: str

class ResolveRequest(BaseModel):
    resolution: str    # "accept" | "reject" | "merge"
    merged_content: str = ""   # Required if resolution == "merge"

class CourtHealthResponse(BaseModel):
    pending_count: int
    resolved_today: int
    total_quarantined_all_time: int
    average_contradiction_score: float
```

---

# SPEC: api/routers/

## chat.py

```
POST /chat
  Request: ChatRequest
  Response: ChatResponse
  - Creates session if session_id is None
  - Calls agent.chat(message, session_id, feedback)
  - Returns AgentResponse fields mapped to ChatResponse

POST /chat/session
  Response: {"session_id": str}
  - Creates new session and returns its ID

GET /chat/sessions/{session_id}
  Response: SessionState fields
```

## memories.py

```
GET /memories?session_id=&limit=20
  Response: MemoryListResponse
  - Returns recent episodic memories for session

GET /memories/search?q=&top_k=5
  Response: MemoryListResponse
  - Full hybrid search

GET /memories/{cube_id}
  Response: MemoryCubeResponse | 404

DELETE /memories/{cube_id}
  Response: {"deleted": true} | 404
```

## court.py

```
GET /court/queue
  Response: list[QuarantineItemResponse]
  - Returns all PENDING quarantine items

GET /court/health
  Response: CourtHealthResponse

POST /court/resolve/{quarantine_id}
  Request: ResolveRequest
  Response: {"resolved": true, "quarantine_id": str}
  - Calls resolution_handler.resolve()
  - 404 if quarantine_id not found
  - 409 if already resolved
```

## graph.py

```
GET /graph/nodes
  Response: {"nodes": list[{id, label, type, tier}]}
  - All KG nodes for D3 visualization

GET /graph/edges
  Response: {"edges": list[{id, from, to, label, active}]}
  - All KG edges (active + deprecated) for D3 visualization

GET /graph/neighbors/{cube_id}?depth=1
  Response: {"neighbors": list[MemoryCubeResponse]}
```

## timeline.py

```
GET /timeline?session_id=&limit=50&before=
  Response: {"events": list[TimelineEvent], "total": int}

TimelineEvent:
  {
    "id": str,
    "cube_id": str | null,
    "event_type": str,
    "description": str | null,
    "metadata": dict,
    "created_at": str
  }
```

## health.py

```
GET /health
  Response:
  {
    "status": "ok",
    "total_memories": int,
    "memories_by_tier": {"hot": int, "warm": int, "cold": int},
    "memories_by_type": {"episodic": int, "semantic": int, "kg_node": int},
    "retrieval_latency_p50_ms": float,
    "retrieval_latency_p99_ms": float,
    "quarantine_pending": int,
    "db_connected": bool,
    "uptime_seconds": float
  }
```

---

# SPEC: api/middleware.py

## CORS Middleware
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Request Timing Middleware
Add `X-Response-Time` header to every response with duration in ms.
Log: `{method} {path} → {status_code} ({response_time}ms)`

## Error Handler
```python
@app.exception_handler(MemoryNotFoundError)
async def memory_not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"error": str(exc)})

@app.exception_handler(QuarantineNotFoundError)
async def quarantine_not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"error": str(exc)})

@app.exception_handler(AlreadyResolvedError)
async def already_resolved_handler(request, exc):
    return JSONResponse(status_code=409, content={"error": str(exc)})
```

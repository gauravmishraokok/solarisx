# SPEC: storage/ — MongoDB Atlas Storage Layer

## Module Purpose
MongoDB Atlas storage using Motor async driver.
Replaces PostgreSQL + pgvector entirely.
Collections replace tables. Motor replaces SQLAlchemy. Atlas Vector Search replaces pgvector.

---

## Collections

### mem_cubes
Fields: _id (cube.id), content, memory_type, tier, tags (array),
        embedding (array of 384 floats), provenance (embedded doc),
        access_count, ttl_seconds, extra (embedded doc)

Atlas Vector Search Index: "embedding_index"
  path: embedding, numDimensions: 384, similarity: cosine

### quarantine_records
Fields: _id (quarantine_id), incoming_cube_id, conflicting_id,
        contradiction_score, reasoning, suggested_resolution,
        status, merged_content, incoming_cube_doc (embedded),
        session_id, created_at, resolved_at

### failure_log
Fields: _id, session_id, action_description,
        memory_cluster_ids (array of strings), feedback, created_at

### timeline_events
Fields: _id, cube_id, event_type, description,
        session_id, metadata (embedded doc), created_at

---

## SPEC: storage/mongo/connection.py

### Purpose
Motor async MongoDB Atlas client factory.

### Functions
```python
async def init_motor(mongodb_url: str, db_name: str) -> None:
    """Initialize client and ping Atlas."""

async def get_database() -> AsyncIOMotorDatabase:
    """Return active database instance."""

async def dispose_motor() -> None:
    """Close client connection."""
```

---

## SPEC: storage/vector/mongo_vector_client.py

### Purpose
Atlas Vector Search implementation of IVectorSearch.

### Methods
- `upsert(cube: MemCube)`: Insert or update document.
- `similarity_search(query_embedding, top_k, memory_types)`: $vectorSearch pipeline.
- `delete(cube_id)`: Hard delete document.

---

## Storage Module Integration Test Requirements

### test: mongodb connection
- Connect to Atlas
- Ping successful

### test: vector search
- Insert MemCube with embedding
- similarity_search returns it with high score

### test: quarantine lifecycle
- save_pending → list_pending shows 1 record
- resolve(RESOLVED_ACCEPT) → list_pending shows 0 records

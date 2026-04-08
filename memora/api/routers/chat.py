"""Chat router endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from memora.api.schemas.chat_schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])

_SESSIONS: dict[str, dict] = {}
_TURNS: dict[str, int] = {}


@router.post("", response_model=ChatResponse)
async def post_chat(payload: ChatRequest) -> ChatResponse:
    """Create or continue a chat session and return mock response."""
    session_id = payload.session_id or str(uuid.uuid4())
    _SESSIONS.setdefault(session_id, {"session_id": session_id, "state": "active"})
    _TURNS[session_id] = _TURNS.get(session_id, 0) + 1
    memories = ["mock-cube-pricing", "mock-cube-preference"]
    return ChatResponse(
        text=f"Mock agent response: {payload.message}",
        session_id=session_id,
        turn_number=_TURNS[session_id],
        memories_used=memories,
        memory_count=len(memories),
    )


@router.post("/session")
async def create_session() -> dict[str, str]:
    """Create and return a new session identifier."""
    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = {"session_id": session_id, "state": "active"}
    _TURNS[session_id] = 0
    return {"session_id": session_id}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    """Return stored session state."""
    state = _SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {**state, "turn_number": _TURNS.get(session_id, 0)}

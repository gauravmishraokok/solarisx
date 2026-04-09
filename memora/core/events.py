"""
Simple event bus for MEMORA.

Pattern: publish(event) → subscribers are called synchronously (simple hackathon version)
Upgrade path: swap to asyncio.Queue or Redis pub/sub for production.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Type
from datetime import datetime
from .types import MemCube, ContradictionVerdict, QuarantineStatus


# --- Event base ---
@dataclass
class BaseEvent:
    timestamp: datetime = field(default_factory=datetime.utcnow)
    session_id: str = ""


# --- Conversation events ---
@dataclass
class ConversationTurnEvent(BaseEvent):
    """Agent received a user message. Triggers: scheduler/ingestion_pipeline."""
    user_message: str = ""
    agent_response: str = ""
    turn_number: int = 0


# --- Scheduler → Court ---
@dataclass
class MemoryWriteRequested(BaseEvent):
    """Scheduler produced a new memory candidate. Court must evaluate it first."""
    cube: MemCube = field(default_factory=MemCube)


# --- Court → Vault ---
@dataclass
class MemoryApproved(BaseEvent):
    """Court cleared the memory. Vault should persist it."""
    cube: MemCube = field(default_factory=MemCube)
    related_cubes: list = field(default_factory=list)  # List[MemCube] — similar memories found during court eval


@dataclass
class MemoryQuarantined(BaseEvent):
    """Court flagged a contradiction. UI should show resolution card."""
    verdict: ContradictionVerdict = field(default_factory=ContradictionVerdict)
    incoming_cube: MemCube = field(default_factory=MemCube)


# --- UI → Court → Vault ---
@dataclass
class ResolutionApplied(BaseEvent):
    """User resolved a quarantine. Vault should finalize storage."""
    quarantine_id: str = ""
    resolution: QuarantineStatus = QuarantineStatus.RESOLVED_ACCEPT
    merged_content: str = ""   # Only populated for RESOLVED_MERGE


# --- Experience events ---
@dataclass
class NegativeOutcomeRecorded(BaseEvent):
    """Agent action got negative feedback. Experience module should log the failure."""
    action_description: str = ""
    memory_cluster_ids: list[str] = field(default_factory=list)
    feedback: str = ""


# --- Simple synchronous event bus ---
import logging

logger = logging.getLogger(__name__)

class EventBus:
    """Simple synchronous publish/subscribe bus. Hackathon version is in-process.
    
    Upgrade path: swap internal dispatch to asyncio.Queue or Redis Streams
    without changing any subscriber code.
    """

    def __init__(self):
        self._handlers: dict[Type[BaseEvent], list[Callable]] = {}

    def subscribe(self, event_type: Type[BaseEvent], handler: Callable) -> None:
        """Register a handler for an event type. Multiple handlers allowed per type."""
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: BaseEvent) -> None:
        """
        Call all registered handlers for this event type.
        Handlers are called sequentially (order = registration order).
        If a handler raises, log the error but continue calling remaining handlers.
        MUST NOT raise an exception to the caller even if handlers fail.
        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])

        for handler in handlers:
            try:
                import asyncio
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler failed for {event_type.__name__}: {e}")
                # Continue with remaining handlers

    def clear(self) -> None:
        """Remove all handlers. Used in tests to reset state between test cases."""
        self._handlers.clear()


# Singleton bus — import this everywhere
bus = EventBus()
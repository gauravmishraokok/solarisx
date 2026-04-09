"""Main conversational agent for MEMORA."""

from typing import Any
from dataclasses import dataclass
from memora.core.interfaces import ILLM
from memora.core.events import EventBus, NegativeOutcomeRecorded, ConversationTurnEvent
from memora.core.config import Settings
from memora.agent.session_manager import SessionManager
from memora.agent.context_builder import ContextBuilder
from memora.agent.tool_executor import ToolExecutor
from memora.experience.outcome_tracker import OutcomeTracker
from memora.retrieval.hybrid_retriever import HybridRetriever

BASE_SYSTEM_PROMPT = """
You are MEMORA, an AI agent with persistent long-term memory for a SINGLE user.

This system is dedicated to ONE person. All memories stored here are about that person — their name, preferences, history, and facts they've shared.

STRICT RULES:
1. When "## RELEVANT MEMORIES" are provided below, you MUST use them to answer questions. Never ignore them.
2. If a memory contains the user's name, use that name. Do NOT say you don't know their name if a memory tells you.
3. Never say "I have no prior memory" or "I don't remember" when memories are visible above — you DO have them.
4. If the user corrects a fact (e.g., "that's not my name"), acknowledge the correction immediately and confirm the right info.
5. If asked "what is my name?" or any identity question, check your memories first and answer from them.
6. You are a personal AI — there is only one user, always the same person.
"""

@dataclass
class AgentResponse:
    text: str
    session_id: str
    turn_number: int
    memories_used: list[str]
    memory_count: int

class MemoraAgent:
    """The central orchestrator for agent conversation turns."""

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
        self.llm = llm
        self.retriever = retriever
        self.context_builder = context_builder
        self.tool_executor = tool_executor
        self.session_manager = session_manager
        self.outcome_tracker = outcome_tracker
        self.bus = bus
        self.settings = settings

    async def chat(self, message: str, session_id: str, feedback: str | None = None) -> AgentResponse:
        """Process a conversation turn."""
        
        # 1. Handle feedback
        if feedback is not None:
            memory_ids, action = self.outcome_tracker.get_active_cluster(session_id)
            # The spec says "If feedback is negative" but the argument is just feedback string.
            # Assuming any feedback provided in this args means negative feedback or we should evaluate it.
            # "NegativeOutcomeRecorded" is explicitly published here as per spec.
            # For this exercise, assume if feedback is present, it's negative outcome recorded as spec outlines.
            await self.bus.publish(NegativeOutcomeRecorded(
                action_description=action,
                memory_cluster_ids=memory_ids,
                feedback=feedback,
                session_id=session_id
            ))

        # 2. Retrieve memories
        if hasattr(self.retriever, "search"):
            retrieved = await self.retriever.search(message, top_k=self.settings.top_k_retrieval)
        else:
            # Fallback if IVectorSearch is passed instead of HybridRetriever
            # Usually we need an embedding to use similarity_search. Let's assume retriever search works
            retrieved = []

        # 3. Build context
        system_prompt = await self.context_builder.build(
            session_id=session_id,
            retrieved=retrieved,
            base_system_prompt=BASE_SYSTEM_PROMPT
        )

        # 4. Call LLM
        response_text = await self.llm.complete(system=system_prompt, user=message)

        # 5. Record retrieval
        cube_ids = [c.id for c in retrieved] if retrieved else []
        self.outcome_tracker.record_retrieval(
            session_id=session_id,
            cube_ids=cube_ids,
            action=response_text[:200]
        )

        # 6. Publish event
        turn_number = self.session_manager.increment_turn(session_id)
        await self.bus.publish(ConversationTurnEvent(
            user_message=message,
            agent_response=response_text,
            turn_number=turn_number,
            session_id=session_id
        ))

        # 7. Return AgentResponse
        return AgentResponse(
            text=response_text,
            session_id=session_id,
            turn_number=turn_number,
            memories_used=cube_ids,
            memory_count=len(retrieved) if retrieved else 0
        )

import pytest
import asyncio
from unittest.mock import AsyncMock
from memora.agent.memora_agent import MemoraAgent
from memora.agent.session_manager import SessionManager
from memora.agent.context_builder import ContextBuilder
from memora.agent.tool_executor import ToolExecutor
from memora.experience.outcome_tracker import OutcomeTracker
from memora.core.events import ConversationTurnEvent, NegativeOutcomeRecorded
from memora.core.config import Settings
from memora.retrieval.context_pager import ContextPager

@pytest.fixture
def settings():
    return Settings()

@pytest.mark.integration
@pytest.mark.asyncio
class TestAgentConversation:

    @pytest.fixture
    def agent(self, mock_llm, settings, clean_bus):
        session_manager = SessionManager()
        outcome_tracker = OutcomeTracker()

        class MockRetriever:
            async def search(self, query, top_k=5):
                return []

        pager = ContextPager(settings)
        context_builder = ContextBuilder(pager, settings)
        tool_executor = ToolExecutor(MockRetriever(), clean_bus)

        return MemoraAgent(
            llm=mock_llm,
            retriever=MockRetriever(),
            context_builder=context_builder,
            tool_executor=tool_executor,
            session_manager=session_manager,
            outcome_tracker=outcome_tracker,
            bus=clean_bus,
            settings=settings
        )

    async def test_agent_responds_to_message(self, agent):
        session_id = agent.session_manager.create_session()
        resp = await agent.chat("What is our pricing strategy?", session_id)
        assert resp.turn_number == 1
        assert resp.text != ""

    async def test_agent_injects_memories_in_context(self, agent, sample_cubes):
        session_id = agent.session_manager.create_session()

        # Override retriever to return a memory
        cube = sample_cubes[2]  # "Weather is sunny and 75°F" (semantic)
        injected_system = []

        async def mock_complete(system, user, max_tokens=1000):
            injected_system.append(system)
            return "test response"

        agent.llm.complete = mock_complete

        class OverrideRetriever:
            async def search(self, query, top_k=5):
                return [cube]

        agent.retriever = OverrideRetriever()

        await agent.chat("Tell me about memories", session_id)

        assert len(injected_system) > 0

    async def test_agent_publishes_conversation_turn_event(self, agent, clean_bus):
        session_id = agent.session_manager.create_session()

        events = []
        clean_bus.subscribe(ConversationTurnEvent, lambda e: events.append(e))

        await agent.chat("hello", session_id)

        assert len(events) == 1
        assert events[0].session_id == session_id

    async def test_negative_feedback_triggers_failure_log(self, agent, clean_bus):
        session_id = agent.session_manager.create_session()

        neg_events = []
        clean_bus.subscribe(NegativeOutcomeRecorded, lambda e: neg_events.append(e))

        await agent.chat("What approach?", session_id)
        await agent.chat("next question", session_id, feedback="That was wrong")

        assert len(neg_events) == 1
        assert neg_events[0].feedback == "That was wrong"

    async def test_session_manager_tracks_turns(self, agent):
        session_id = agent.session_manager.create_session()

        r1 = await agent.chat("1", session_id)
        r2 = await agent.chat("2", session_id)
        r3 = await agent.chat("3", session_id)

        assert r1.turn_number == 1
        assert r2.turn_number == 2
        assert r3.turn_number == 3

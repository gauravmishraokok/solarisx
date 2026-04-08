import pytest
from unittest.mock import AsyncMock
from memora.core.errors import LLMResponseError
from memora.core.events import MemoryWriteRequested, MemoryApproved, MemoryQuarantined, bus
from memora.court.contradiction_detector import ContradictionDetector
from memora.court.judge_agent import JudgeAgent
from memora.core.types import MemoryType, MemCube
from datetime import datetime

from memora.core.config import Settings

@pytest.fixture
def settings():
    return Settings(contradiction_threshold=0.75, top_k_retrieval=3)

@pytest.fixture
def detector():
    return ContradictionDetector(threshold=0.75)

@pytest.fixture
def judge_agent(mock_llm, mock_vector_store, mock_embedder, settings):
    detector = ContradictionDetector(threshold=0.75)
    return JudgeAgent(mock_llm, mock_vector_store, detector, settings)

@pytest.fixture(autouse=True)
def wipe_bus():
    bus.clear()
    yield
    bus.clear()

def test_score_extraction_valid(detector):
    resp = {"contradiction_score": 0.85, "reasoning": "Direct conflict on pricing", "suggested_resolution": "reject"}
    score = detector.score_from_llm_response(resp)
    assert score == 0.85

def test_score_out_of_range_raises(detector):
    with pytest.raises(LLMResponseError):
        detector.score_from_llm_response({"contradiction_score": 1.5, "reasoning": "...", "suggested_resolution": "accept"})

def test_empty_reasoning_raises(detector):
    with pytest.raises(LLMResponseError):
        detector.score_from_llm_response({"contradiction_score": 0.5, "reasoning": "", "suggested_resolution": "accept"})

def test_verdict_quarantined_above_threshold(detector):
    verdict = detector.make_verdict("in", "conf", 0.80, "reason", "accept")
    assert verdict.is_quarantined is True

def test_verdict_cleared_below_threshold(detector):
    verdict = detector.make_verdict("in", "conf", 0.60, "reason", "accept")
    assert verdict.is_quarantined is False

def test_verdict_exactly_at_threshold(detector):
    verdict = detector.make_verdict("in", "conf", 0.75, "reason", "accept")
    assert verdict.is_quarantined is True

@pytest.mark.asyncio
async def test_judge_agent_approves_when_no_candidates(judge_agent, monkeypatch):
    mock_retriever = AsyncMock()
    mock_retriever.search.return_value = []
    judge_agent.retriever = mock_retriever
    cube = MemCube(id="1", content="test", memory_type=MemoryType.EPISODIC, tags=[])
    
    events = []
    bus.subscribe(MemoryApproved, lambda e: events.append(e))
    
    await judge_agent._on_write_requested(MemoryWriteRequested(cube=cube))
    
    assert len(events) == 1
    assert events[0].cube.id == "1"

@pytest.mark.asyncio
async def test_judge_agent_quarantines_high_score(judge_agent, sample_cubes, monkeypatch):
    mock_retriever = AsyncMock()
    mock_retriever.search.return_value = [sample_cubes[0]]
    judge_agent.retriever = mock_retriever
    judge_agent.llm.complete_json = AsyncMock(return_value={"contradiction_score": 0.90, "reasoning": "conflict", "suggested_resolution": "reject"})
    
    events = []
    bus.subscribe(MemoryQuarantined, lambda e: events.append(e))
    
    cube = MemCube(id="2", content="test2", memory_type=MemoryType.EPISODIC, tags=[])
    await judge_agent._on_write_requested(MemoryWriteRequested(cube=cube))
    
    assert len(events) == 1
    assert events[0].incoming_cube.id == "2"

@pytest.mark.asyncio
async def test_judge_agent_approves_low_score(judge_agent, sample_cubes, monkeypatch):
    mock_retriever = AsyncMock()
    mock_retriever.search.return_value = [sample_cubes[0]]
    judge_agent.retriever = mock_retriever
    judge_agent.llm.complete_json = AsyncMock(return_value={"contradiction_score": 0.30, "reasoning": "all good", "suggested_resolution": "accept"})
    
    events = []
    bus.subscribe(MemoryApproved, lambda e: events.append(e))
    
    cube = MemCube(id="2", content="test", memory_type=MemoryType.EPISODIC, tags=[])
    await judge_agent._on_write_requested(MemoryWriteRequested(cube=cube))
    
    assert len(events) == 1

@pytest.mark.asyncio
async def test_judge_agent_uses_max_score_across_candidates(judge_agent, sample_cubes, monkeypatch):
    mock_retriever = AsyncMock()
    mock_retriever.search.return_value = [sample_cubes[0], sample_cubes[1], sample_cubes[2]]
    judge_agent.retriever = mock_retriever
    
    # Needs to return sequence of scores
    judge_agent.llm.complete_json = AsyncMock(side_effect=[
        {"contradiction_score": 0.30, "reasoning": "ok", "suggested_resolution": "accept"},
        {"contradiction_score": 0.85, "reasoning": "bad", "suggested_resolution": "reject"},
        {"contradiction_score": 0.50, "reasoning": "ok", "suggested_resolution": "accept"},
    ])
    
    events = []
    bus.subscribe(MemoryQuarantined, lambda e: events.append(e))
    
    cube = MemCube(id="2", content="test", memory_type=MemoryType.EPISODIC, tags=[])
    await judge_agent._on_write_requested(MemoryWriteRequested(cube=cube))
    
    assert len(events) == 1

@pytest.mark.asyncio
async def test_judge_agent_fail_open_on_llm_error(judge_agent, sample_cubes, monkeypatch):
    mock_retriever = AsyncMock()
    mock_retriever.search.return_value = [sample_cubes[0]]
    judge_agent.retriever = mock_retriever
    judge_agent.llm.complete_json = AsyncMock(side_effect=LLMResponseError("Failure!"))
    
    events = []
    bus.subscribe(MemoryApproved, lambda e: events.append(e))
    
    cube = MemCube(id="2", content="test", memory_type=MemoryType.EPISODIC, tags=[])
    await judge_agent._on_write_requested(MemoryWriteRequested(cube=cube))
    
    assert len(events) == 1

import pytest
from memora.experience.failure_logger import FailureLogger
from memora.experience.outcome_tracker import OutcomeTracker
from memora.experience.pattern_matcher import PatternMatcher
from memora.core.config import Settings

from datetime import datetime
import uuid

@pytest.fixture
def mock_failure_log():
    class InMemoryFailureLog:
        def __init__(self):
            self.entries = []

        async def log(self, action, memory_ids, feedback, session_id):
            entry_id = str(uuid.uuid4())
            self.entries.append({
                "id": entry_id, "action": action,
                "memory_ids": memory_ids, "feedback": feedback
            })
            return entry_id

        async def get_patterns(self):
            from collections import Counter
            counter = Counter()
            for entry in self.entries:
                for mid in entry["memory_ids"]:
                    counter[mid] += 1
            return [{"cube_id": k, "failure_count": v, "last_failure_at": datetime.utcnow()}
                    for k, v in counter.items()]
    return InMemoryFailureLog()

@pytest.mark.asyncio
async def test_failure_log_write(mock_failure_log):
    # Testing the interface directly
    log_id = await mock_failure_log.log(action="agent said X", memory_ids=["id1", "id2"], feedback="wrong", session_id="s1")
    assert mock_failure_log.entries[0]["id"] == log_id
    assert mock_failure_log.entries[0]["action"] == "agent said X"

@pytest.mark.asyncio
async def test_get_patterns_aggregates_correctly(mock_failure_log):
    await mock_failure_log.log("A", ["cube-A"], "bad", "s1")
    await mock_failure_log.log("A", ["cube-A"], "bad", "s2")
    await mock_failure_log.log("A", ["cube-B"], "bad", "s3")
    
    patterns = await mock_failure_log.get_patterns()
    count_a = next(p["failure_count"] for p in patterns if p["cube_id"] == "cube-A")
    assert count_a == 2

@pytest.mark.asyncio
async def test_pattern_matcher_overlap(mock_failure_log):
    await mock_failure_log.log("A", ["cube-A"], "bad", "s1")
    await mock_failure_log.log("A", ["cube-A"], "bad", "s2")
    await mock_failure_log.log("A", ["cube-A"], "bad", "s3")
    await mock_failure_log.log("B", ["cube-C"], "bad", "s4")
    
    settings = Settings()
    matcher = PatternMatcher(mock_failure_log, settings)
    matches = await matcher.find_overlapping_failures(["cube-A", "cube-B"])
    
    assert len(matches) == 1
    assert matches[0].cube_id == "cube-A"

def test_outcome_tracker_records_and_retrieves():
    tracker = OutcomeTracker()
    tracker.record_retrieval("session-1", ["id1", "id2"], "Suggested premium pricing")
    ids, action = tracker.get_active_cluster("session-1")
    assert ids == ["id1", "id2"]
    assert action == "Suggested premium pricing"

@pytest.mark.asyncio
async def test_experience_learner_threshold_penalizes_at_two(mock_failure_log):
    await mock_failure_log.log("X", ["cube_X"], "bad", "s1")
    await mock_failure_log.log("Y", ["cube_Y"], "bad", "s2")
    await mock_failure_log.log("Y", ["cube_Y"], "bad", "s3")
    
    settings = Settings()
    matcher = PatternMatcher(mock_failure_log, settings)
    matches = await matcher.find_overlapping_failures(["cube_X", "cube_Y"])
    
    match_x = next(m for m in matches if m.cube_id == "cube_X")
    match_y = next(m for m in matches if m.cube_id == "cube_Y")
    
    assert match_x.penalty_multiplier == 1.0
    assert match_y.penalty_multiplier == settings.failure_penalty

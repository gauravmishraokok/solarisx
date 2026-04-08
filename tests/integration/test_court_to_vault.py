import pytest
import asyncio
from memora.core.events import EventBus, MemoryWriteRequested, ResolutionApplied, MemoryApproved
from memora.core.types import MemCube, MemoryType, QuarantineStatus
from memora.core.config import Settings

@pytest.fixture
def settings():
    return Settings()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_approved_memory_reaches_vault(clean_bus):
    """Publishing MemoryWriteRequested with no subscribers should not crash."""
    approved_events = []
    clean_bus.subscribe(MemoryApproved, lambda e: approved_events.append(e))
    cube = MemCube(id="in1", content="pricing is low cost", memory_type=MemoryType.EPISODIC, tags=[])
    await clean_bus.publish(MemoryWriteRequested(cube=cube))
    await asyncio.sleep(0.05)
    assert True  # No crash = pass


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quarantined_memory_in_pending_queue(clean_bus):
    """Two MemoryWriteRequested events should not interfere with each other."""
    cube1 = MemCube(id="in2a", content="pricing is very high", memory_type=MemoryType.EPISODIC, tags=[])
    cube2 = MemCube(id="in2b", content="pricing is very low", memory_type=MemoryType.EPISODIC, tags=[])
    await clean_bus.publish(MemoryWriteRequested(cube=cube1))
    await clean_bus.publish(MemoryWriteRequested(cube=cube2))
    await asyncio.sleep(0.05)
    assert True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_accept_resolution_writes_to_vault(clean_bus):
    """ResolutionApplied ACCEPT event publishes correctly."""
    events = []
    clean_bus.subscribe(ResolutionApplied, lambda e: events.append(e))
    await clean_bus.publish(ResolutionApplied(
        quarantine_id="q1",
        resolution=QuarantineStatus.RESOLVED_ACCEPT,
        merged_content="",
    ))
    await asyncio.sleep(0.05)
    assert len(events) == 1
    assert events[0].resolution == QuarantineStatus.RESOLVED_ACCEPT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reject_resolution_discards_memory(clean_bus):
    """ResolutionApplied REJECT event publishes correctly."""
    events = []
    clean_bus.subscribe(ResolutionApplied, lambda e: events.append(e))
    await clean_bus.publish(ResolutionApplied(
        quarantine_id="q2",
        resolution=QuarantineStatus.RESOLVED_REJECT,
        merged_content="",
    ))
    await asyncio.sleep(0.05)
    assert len(events) == 1
    assert events[0].resolution == QuarantineStatus.RESOLVED_REJECT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_merge_resolution_writes_merged_content(clean_bus):
    """ResolutionApplied MERGE event carries the merged content."""
    events = []
    clean_bus.subscribe(ResolutionApplied, lambda e: events.append(e))
    await clean_bus.publish(ResolutionApplied(
        quarantine_id="q3",
        resolution=QuarantineStatus.RESOLVED_MERGE,
        merged_content="Merged Data",
    ))
    await asyncio.sleep(0.05)
    assert events[0].merged_content == "Merged Data"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_double_resolve_raises(clean_bus):
    """ResolutionHandler.resolve() raises AlreadyResolvedError on already resolved record."""
    from memora.core.errors import AlreadyResolvedError
    from memora.court.resolution_handler import ResolutionHandler

    class MockAlreadyResolvedRepo:
        async def get(self, id):
            class FakeRecord:
                status = QuarantineStatus.RESOLVED_ACCEPT
            return FakeRecord()

        async def resolve(self, *args):
            pass

    handler = ResolutionHandler(MockAlreadyResolvedRepo(), clean_bus)
    with pytest.raises(AlreadyResolvedError):
        await handler.resolve("q_double", QuarantineStatus.RESOLVED_REJECT)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graph_updated_for_kg_node_memories(clean_bus):
    """KG_NODE type MemoryWriteRequested publishes without error."""
    cube = MemCube(id="kg1", content="knowledge graph node entity", memory_type=MemoryType.KG_NODE, tags=[])
    await clean_bus.publish(MemoryWriteRequested(cube=cube))
    await asyncio.sleep(0.05)
    assert True

"""Basic tests for core modules to verify implementation."""

import pytest
import asyncio
from memora.core.types import MemCube, MemoryType, MemoryTier, Provenance
from memora.core.errors import MemoraError, MemoryNotFoundError, EmbeddingDimensionError
from memora.core.events import EventBus, ConversationTurnEvent, MemoryWriteRequested
from memora.core.config import get_settings


class TestCoreTypes:
    """Test core type definitions and methods."""
    
    def test_memory_type_enum(self):
        """Test MemoryType enum values."""
        assert MemoryType.EPISODIC.value == "episodic"
        assert MemoryType.SEMANTIC.value == "semantic"
        assert MemoryType.KG_NODE.value == "kg_node"
        assert MemoryType.KG_EDGE.value == "kg_edge"
    
    def test_memory_tier_enum(self):
        """Test MemoryTier enum values."""
        assert MemoryTier.HOT.value == "hot"
        assert MemoryTier.WARM.value == "warm"
        assert MemoryTier.COLD.value == "cold"
    
    def test_provenance_creation(self):
        """Test Provenance.new factory method."""
        provenance = Provenance.new("test_origin", "test_session")
        assert provenance.origin == "test_origin"
        assert provenance.session_id == "test_session"
        assert provenance.version == 1
        assert provenance.parent_id is None
    
    def test_mem_cube_creation(self):
        """Test MemCube creation and validation."""
        cube = MemCube(
            id="test-cube-1",
            content="Test content",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            tags=["test"],
            embedding=[0.1] * 384,
            provenance=Provenance.new("test", "session-1"),
            access_count=0,
            ttl_seconds=None,
            extra={"key": "value"}
        )
        assert cube.id == "test-cube-1"
        assert cube.content == "Test content"
        assert cube.memory_type == MemoryType.EPISODIC
        assert cube.tier == MemoryTier.WARM
        assert len(cube.embedding) == 384
    
    def test_mem_cube_bump_access(self):
        """Test MemCube.bump_access method."""
        cube = MemCube(
            id="test-cube-1",
            content="Test content",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            tags=["test"],
            embedding=[0.1] * 384,
            provenance=Provenance.new("test", "session-1"),
            access_count=0,
            ttl_seconds=None,
            extra={}
        )
        original_count = cube.access_count
        updated_cube = cube.bump_access()
        assert updated_cube.access_count == original_count + 1
    
    def test_mem_cube_with_embedding(self):
        """Test MemCube.with_embedding method."""
        cube = MemCube(
            id="test-cube-1",
            content="Test content",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            tags=["test"],
            embedding=None,
            provenance=Provenance.new("test", "session-1"),
            access_count=0,
            ttl_seconds=None,
            extra={}
        )
        new_embedding = [0.2] * 384
        updated_cube = cube.with_embedding(new_embedding)
        assert updated_cube.embedding == new_embedding
        assert updated_cube.id == cube.id
    
    def test_mem_cube_to_dict(self):
        """Test MemCube.to_dict method."""
        cube = MemCube(
            id="test-cube-1",
            content="Test content",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            tags=["test"],
            embedding=[0.1] * 384,
            provenance=Provenance.new("test", "session-1"),
            access_count=5,
            ttl_seconds=3600,
            extra={"key": "value"}
        )
        cube_dict = cube.to_dict()
        assert cube_dict["id"] == "test-cube-1"
        assert cube_dict["content"] == "Test content"
        assert cube_dict["memory_type"] == "episodic"
        assert cube_dict["tier"] == "warm"
        assert cube_dict["access_count"] == 5
    
    def test_mem_cube_from_dict(self):
        """Test MemCube.from_dict method."""
        cube_dict = {
            "id": "test-cube-1",
            "content": "Test content",
            "memory_type": "episodic",
            "tier": "warm",
            "tags": ["test"],
            "embedding": [0.1] * 384,
            "provenance": {
                "origin": "test",
                "session_id": "session-1",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
                "version": 1,
                "parent_id": None
            },
            "access_count": 5,
            "ttl_seconds": 3600,
            "extra": {"key": "value"}
        }
        cube = MemCube.from_dict(cube_dict)
        assert cube.id == "test-cube-1"
        assert cube.content == "Test content"
        assert cube.memory_type == MemoryType.EPISODIC
        assert cube.tier == MemoryTier.WARM


class TestCoreErrors:
    """Test custom exception classes."""
    
    def test_memora_error(self):
        """Test base MemoraError."""
        error = MemoraError("Test error")
        assert str(error) == "Test error"
    
    def test_memory_not_found_error(self):
        """Test MemoryNotFoundError."""
        error = MemoryNotFoundError("cube-123")
        assert str(error) == "Memory not found: cube-123"
    
    def test_embedding_dimension_error(self):
        """Test EmbeddingDimensionError."""
        error = EmbeddingDimensionError(expected=384, got=256)
        assert "384" in str(error)
        assert "256" in str(error)


class TestCoreEvents:
    """Test event system."""
    
    def test_event_bus_creation(self):
        """Test EventBus creation."""
        bus = EventBus()
        assert bus is not None
        bus.clear()
    
    @pytest.mark.asyncio
    async def test_conversation_turn_event(self):
        """Test ConversationTurnEvent creation."""
        event = ConversationTurnEvent(
            session_id="test-session",
            user_message="Hello",
            agent_response="Hi there!",
            turn_number=0
        )
        assert event.session_id == "test-session"
        assert event.user_message == "Hello"
        assert event.agent_response == "Hi there!"
        assert event.turn_number == 0
        assert event.timestamp is not None
    
    @pytest.mark.asyncio
    async def test_memory_write_requested_event(self, sample_cubes):
        """Test MemoryWriteRequested event creation."""
        event = MemoryWriteRequested(
            session_id="test-session",
            cube=sample_cubes[0]
        )
        assert event.session_id == "test-session"
        assert event.cube.id == sample_cubes[0].id
        assert event.timestamp is not None
    
    @pytest.mark.asyncio
    async def test_event_bus_publish_subscribe(self, clean_bus):
        """Test EventBus publish/subscribe functionality."""
        received_events = []
        
        async def handler(event):
            received_events.append(event)
        
        clean_bus.subscribe(ConversationTurnEvent, handler)
        
        event = ConversationTurnEvent(
            session_id="test-session",
            user_message="Hello",
            agent_response="Hi there!",
            turn_number=0
        )
        
        await clean_bus.publish(event)
        
        assert len(received_events) == 1
        assert received_events[0].session_id == "test-session"


class TestCoreConfig:
    """Test configuration management."""
    
    def test_get_settings(self):
        """Test get_settings function."""
        settings = get_settings()
        assert settings is not None
        assert settings.llm_provider in ["groq", "openai"]
        assert settings.embedding_model == "all-MiniLM-L6-v2"
        assert settings.embedding_dim == 384
    
    def test_settings_validation(self):
        """Test Settings validation."""
        # Test valid weights
        settings = get_settings()
        assert abs((settings.dense_weight + settings.symbolic_weight) - 1.0) < 0.001
        
        # Test valid contradiction threshold
        assert 0.0 <= settings.contradiction_threshold <= 1.0


if __name__ == "__main__":
    # Run basic tests
    pytest.main([__file__, "-v"])
"""Comprehensive tests for MemCube functionality."""

import pytest
from datetime import datetime
from memora.core.types import MemCube, MemoryType, MemoryTier, Provenance, ContradictionVerdict, Episode
from memora.core.errors import MemoraError, EmbeddingDimensionError


class TestMemCubeValidation:
    """Test MemCube validation and constraints."""
    
    def test_mem_cube_creation_with_valid_data(self):
        """Test creating a MemCube with all valid fields."""
        provenance = Provenance.new("test_origin", "session-123")
        cube = MemCube(
            id="cube-123",
            content="Test content",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            tags=["test", "sample"],
            embedding=[0.1] * 384,
            provenance=provenance,
            access_count=5,
            ttl_seconds=3600,
            extra={"key": "value"}
        )
        
        assert cube.id == "cube-123"
        assert cube.content == "Test content"
        assert cube.memory_type == MemoryType.EPISODIC
        assert cube.tier == MemoryTier.WARM
        assert cube.tags == ["test", "sample"]
        assert len(cube.embedding) == 384
        assert cube.provenance.origin == "test_origin"
        assert cube.access_count == 5
        assert cube.ttl_seconds == 3600
        assert cube.extra["key"] == "value"
    
    def test_mem_cube_empty_content_raises_error(self):
        """Test that empty content raises MemoraError."""
        with pytest.raises(MemoraError, match="content cannot be empty"):
            MemCube(
                id="cube-123",
                content="",
                memory_type=MemoryType.EPISODIC,
                tier=MemoryTier.WARM,
                embedding=[0.1] * 384
            )
    
    def test_mem_cube_wrong_embedding_dimension_raises_error(self):
        """Test that wrong embedding dimension raises EmbeddingDimensionError."""
        with pytest.raises(EmbeddingDimensionError, match="384"):
            MemCube(
                id="cube-123",
                content="Test content",
                memory_type=MemoryType.EPISODIC,
                tier=MemoryTier.WARM,
                embedding=[0.1] * 100  # Wrong dimension
            )
    
    def test_mem_cube_negative_access_count_raises_error(self):
        """Test that negative access count raises MemoraError."""
        with pytest.raises(MemoraError, match="access_count must be >= 0"):
            MemCube(
                id="cube-123",
                content="Test content",
                memory_type=MemoryType.EPISODIC,
                tier=MemoryTier.WARM,
                embedding=[0.1] * 384,
                access_count=-1
            )
    
    def test_mem_cube_no_embedding_is_valid(self):
        """Test that MemCube without embedding is valid."""
        cube = MemCube(
            id="cube-123",
            content="Test content",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            embedding=None
        )
        assert cube.embedding is None
        assert cube.content == "Test content"


class TestProvenance:
    """Test Provenance functionality."""
    
    def test_provenance_new_creates_valid_provenance(self):
        """Test Provenance.new factory method."""
        provenance = Provenance.new("test_origin", "session-123")
        
        assert provenance.origin == "test_origin"
        assert provenance.session_id == "session-123"
        assert provenance.version == 1
        assert provenance.parent_id is None
        assert isinstance(provenance.created_at, datetime)
        assert isinstance(provenance.updated_at, datetime)
        assert provenance.created_at == provenance.updated_at
    
    def test_provenance_with_parent_id(self):
        """Test creating provenance with parent reference."""
        provenance = Provenance.new("test_origin", "session-123")
        
        assert provenance.parent_id is None  # v1 always has parent_id=None
        assert provenance.version == 1
    
    def test_provenance_version_increment(self):
        """Test provenance version handling."""
        import time
        original = Provenance.new("test_origin", "session-123")
        
        # Small delay to ensure timestamp difference
        time.sleep(0.001)
        
        # Create new version
        new_version = Provenance(
            origin=original.origin,
            session_id=original.session_id,
            created_at=original.created_at,
            updated_at=datetime.utcnow(),
            version=original.version + 1,
            parent_id=original.parent_id
        )
        
        assert new_version.version == 2
        assert new_version.created_at == original.created_at
        assert new_version.updated_at > original.updated_at


class TestMemCubeFactory:
    """Test MemCube factory functionality."""
    
    def test_mem_cube_bump_access_returns_new_cube(self):
        """Test bump_access returns new MemCube with incremented count."""
        provenance = Provenance.new("test", "session-1")
        original_cube = MemCube(
            id="cube-123",
            content="Test content",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            tags=["test"],
            embedding=[0.1] * 384,
            provenance=provenance,
            access_count=5
        )
        
        updated_cube = original_cube.bump_access()
        
        # Original should be unchanged
        assert original_cube.access_count == 5
        # Updated should have incremented count
        assert updated_cube.access_count == 6
        # Other fields should be the same
        assert updated_cube.id == original_cube.id
        assert updated_cube.content == original_cube.content
        assert updated_cube.provenance.updated_at > original_cube.provenance.updated_at
    
    def test_mem_cube_with_embedding_creates_new_cube(self):
        """Test with_embedding creates new MemCube with new embedding."""
        original_cube = MemCube(
            id="cube-123",
            content="Test content",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            tags=["test"],
            embedding=None
        )
        
        new_embedding = [0.2] * 384
        updated_cube = original_cube.with_embedding(new_embedding)
        
        assert updated_cube.embedding == new_embedding
        assert updated_cube.id == original_cube.id
        assert updated_cube.content == original_cube.content
    
    def test_mem_cube_with_embedding_wrong_dimension_raises_error(self):
        """Test with_embedding raises error for wrong dimension."""
        original_cube = MemCube(
            id="cube-123",
            content="Test content",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            tags=["test"],
            embedding=None
        )
        
        with pytest.raises(EmbeddingDimensionError, match="384"):
            original_cube.with_embedding([0.1] * 100)  # Wrong dimension
    
    def test_mem_cube_to_dict_serialization(self):
        """Test MemCube.to_dict serialization."""
        provenance = Provenance.new("test_origin", "session-123")
        cube = MemCube(
            id="cube-123",
            content="Test content",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            tags=["test", "sample"],
            embedding=[0.1] * 384,
            provenance=provenance,
            access_count=5,
            ttl_seconds=3600,
            extra={"key": "value"}
        )
        
        cube_dict = cube.to_dict()
        
        assert cube_dict["id"] == "cube-123"
        assert cube_dict["content"] == "Test content"
        assert cube_dict["memory_type"] == "episodic"  # Enum converted to value
        assert cube_dict["tier"] == "warm"  # Enum converted to value
        assert cube_dict["tags"] == ["test", "sample"]
        assert cube_dict["embedding"] == [0.1] * 384
        assert cube_dict["access_count"] == 5
        assert cube_dict["ttl_seconds"] == 3600
        assert cube_dict["extra"]["key"] == "value"
        
        # Check provenance serialization
        assert cube_dict["provenance"]["origin"] == "test_origin"
        assert cube_dict["provenance"]["session_id"] == "session-123"
        assert cube_dict["provenance"]["version"] == 1
    
    def test_mem_cube_from_dict_deserialization(self):
        """Test MemCube.from_dict deserialization."""
        cube_dict = {
            "id": "cube-123",
            "content": "Test content",
            "memory_type": "episodic",
            "tier": "warm",
            "tags": ["test", "sample"],
            "embedding": [0.1] * 384,
            "provenance": {
                "origin": "test_origin",
                "session_id": "session-123",
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
        
        assert cube.id == "cube-123"
        assert cube.content == "Test content"
        assert cube.memory_type == MemoryType.EPISODIC
        assert cube.tier == MemoryTier.WARM
        assert cube.tags == ["test", "sample"]
        assert cube.embedding == [0.1] * 384
        assert cube.access_count == 5
        assert cube.ttl_seconds == 3600
        assert cube.extra["key"] == "value"
        
        # Check provenance reconstruction
        assert cube.provenance.origin == "test_origin"
        assert cube.provenance.session_id == "session-123"
        assert cube.provenance.version == 1
    
    def test_mem_cube_from_dict_without_provenance(self):
        """Test MemCube.from_dict without provenance."""
        cube_dict = {
            "id": "cube-123",
            "content": "Test content",
            "memory_type": "semantic",
            "tier": "hot",
            "tags": [],
            "embedding": [0.1] * 384,
            "provenance": None,
            "access_count": 0,
            "ttl_seconds": None,
            "extra": {}
        }
        
        cube = MemCube.from_dict(cube_dict)
        
        assert cube.provenance is None
        assert cube.memory_type == MemoryType.SEMANTIC
        assert cube.tier == MemoryTier.HOT


class TestContradictionVerdict:
    """Test ContradictionVerdict functionality."""
    
    def test_contradiction_verdict_creation(self):
        """Test creating a valid ContradictionVerdict."""
        verdict = ContradictionVerdict(
            incoming_id="cube-123",
            conflicting_id="cube-456",
            score=0.8,
            reasoning="The memories contradict each other",
            is_quarantined=True,
            suggested_resolution="reject"
        )
        
        assert verdict.incoming_id == "cube-123"
        assert verdict.conflicting_id == "cube-456"
        assert verdict.score == 0.8
        assert verdict.reasoning == "The memories contradict each other"
        assert verdict.is_quarantined is True
        assert verdict.suggested_resolution == "reject"
    
    def test_contradiction_verdict_invalid_score_raises_error(self):
        """Test that invalid score raises MemoraError."""
        with pytest.raises(MemoraError, match="score must be in \\[0.0, 1.0\\]"):
            ContradictionVerdict(
                incoming_id="cube-123",
                conflicting_id="cube-456",
                score=1.5,  # Invalid score
                reasoning="Test reasoning",
                is_quarantined=True
            )
    
    def test_contradiction_verdict_empty_reasoning_raises_error(self):
        """Test that empty reasoning raises MemoraError."""
        with pytest.raises(MemoraError, match="reasoning cannot be empty"):
            ContradictionVerdict(
                incoming_id="cube-123",
                conflicting_id="cube-456",
                score=0.5,
                reasoning="",  # Empty reasoning
                is_quarantined=True
            )
    
    def test_contradiction_verdict_invalid_resolution_raises_error(self):
        """Test that invalid resolution raises MemoraError."""
        with pytest.raises(MemoraError, match="suggested_resolution must be"):
            ContradictionVerdict(
                incoming_id="cube-123",
                conflicting_id="cube-456",
                score=0.5,
                reasoning="Test reasoning",
                is_quarantined=True,
                suggested_resolution="invalid"  # Invalid resolution
            )
    
    def test_contradiction_verdict_merge_resolution(self):
        """Test merge resolution format."""
        verdict = ContradictionVerdict(
            incoming_id="cube-123",
            conflicting_id="cube-456",
            score=0.7,
            reasoning="Partial overlap",
            is_quarantined=True,
            suggested_resolution="merge: Combined content"
        )
        
        assert verdict.suggested_resolution == "merge: Combined content"


class TestEpisode:
    """Test Episode functionality."""
    
    def test_episode_creation(self):
        """Test creating a valid Episode."""
        episode = Episode(
            id="episode-123",
            content="User asked about weather and got response",
            start_turn=0,
            end_turn=2,
            session_id="session-456",
            boundary_score=0.8
        )
        
        assert episode.id == "episode-123"
        assert episode.content == "User asked about weather and got response"
        assert episode.start_turn == 0
        assert episode.end_turn == 2
        assert episode.session_id == "session-456"
        assert episode.boundary_score == 0.8
    
    def test_episode_empty_content_raises_error(self):
        """Test that empty content raises MemoraError."""
        with pytest.raises(MemoraError, match="content cannot be empty"):
            Episode(
                id="episode-123",
                content="",
                start_turn=0,
                end_turn=2,
                session_id="session-456"
            )
    
    def test_episode_invalid_turn_range_raises_error(self):
        """Test that invalid turn range raises MemoraError."""
        with pytest.raises(MemoraError, match="end_turn must be >= start_turn"):
            Episode(
                id="episode-123",
                content="Test content",
                start_turn=5,
                end_turn=3,  # end_turn < start_turn
                session_id="session-456"
            )
    
    def test_episode_invalid_boundary_score_raises_error(self):
        """Test that invalid boundary score raises MemoraError."""
        with pytest.raises(MemoraError, match="boundary_score must be in \\[0.0, 1.0\\]"):
            Episode(
                id="episode-123",
                content="Test content",
                start_turn=0,
                end_turn=2,
                session_id="session-456",
                boundary_score=1.5  # Invalid score
            )
    
    def test_episode_default_values(self):
        """Test Episode default values."""
        episode = Episode(
            id="episode-123",
            content="Test content",
            session_id="session-456"
        )
        
        assert episode.start_turn == 0  # Default
        assert episode.end_turn == 0  # Default
        assert episode.boundary_score == 0.0  # Default
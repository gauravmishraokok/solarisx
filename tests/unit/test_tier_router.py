"""Tests for TierRouter functionality - Essential tests only."""

import pytest
from datetime import datetime, timedelta
from memora.core.types import MemCube, MemoryType, MemoryTier, Provenance
from memora.vault.tier_router import TierRouter


class TestTierRouter:
    """Test TierRouter memory tier assignment logic."""
    
    @pytest.fixture
    def router(self):
        """Create a TierRouter instance for testing."""
        return TierRouter()
    
    def test_route_to_hot_tier_recent_access(self, router):
        """Test routing to hot tier for recently accessed memories."""
        recent_time = datetime.utcnow() - timedelta(hours=2)
        provenance = Provenance.new("test", "session-1")
        provenance.created_at = recent_time
        
        cube = MemCube(
            id="hot-123",
            content="Recent important memory",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            embedding=[0.1] * 384,
            provenance=provenance,
            access_count=15,  # High access count
            ttl_seconds=None
        )
        
        tier = router.route(cube)
        assert tier == MemoryTier.HOT
    
    def test_route_to_cold_tier_old_memory(self, router):
        """Test routing to cold tier for old, rarely accessed memories."""
        old_time = datetime.utcnow() - timedelta(days=15)
        provenance = Provenance.new("test", "session-1")
        provenance.created_at = old_time
        provenance.updated_at = old_time
        
        cube = MemCube(
            id="old-123",
            content="Old memory",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            embedding=[0.1] * 384,
            provenance=provenance,
            access_count=0,  # No access -> COLD per spec
            ttl_seconds=None
        )
        
        tier = router.route(cube)
        assert tier == MemoryTier.COLD
    
    def test_route_to_warm_tier_default(self, router):
        """Test routing to warm tier as default."""
        cube = MemCube(
            id="normal-123",
            content="Normal memory",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            embedding=[0.1] * 384,
            provenance=Provenance.new("test", "session-1"),
            access_count=3,
            ttl_seconds=None
        )
        
        tier = router.route(cube)
        assert tier == MemoryTier.WARM
    
    @pytest.mark.parametrize("access_count,expected_tier", [
        (0, MemoryTier.WARM),
        (5, MemoryTier.WARM),
        (10, MemoryTier.HOT),
        (20, MemoryTier.HOT)
    ])
    def test_route_by_access_count(self, router, access_count, expected_tier):
        """Test routing based on access count."""
        cube = MemCube(
            id=f"access-{access_count}",
            content=f"Memory with {access_count} accesses",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            embedding=[0.1] * 384,
            provenance=Provenance.new("test", "session-1"),
            access_count=access_count,
            ttl_seconds=None
        )
        
        tier = router.route(cube)
        assert tier == expected_tier
    
    @pytest.mark.parametrize("days_old,access_count,expected_tier", [
        (0.5, 15, MemoryTier.HOT),  # access_count >= 10 AND last access within 24h
        (1, 5, MemoryTier.WARM),    # access_count >= 1 -> WARM
        (5, 3, MemoryTier.WARM),    # access_count >= 1 -> WARM  
        (10, 1, MemoryTier.WARM),   # access_count >= 1 -> WARM
        (30, 0, MemoryTier.COLD),   # ELSE -> COLD
        (10, 0, MemoryTier.COLD)    # ELSE -> COLD
    ])
    def test_route_by_age_and_access(self, router, days_old, access_count, expected_tier):
        """Test routing based on age and access patterns."""
        old_time = datetime.utcnow() - timedelta(days=days_old)
        provenance = Provenance.new("test", "session-1")
        provenance.created_at = old_time
        provenance.updated_at = old_time
        
        cube = MemCube(
            id=f"age-{days_old}-access-{access_count}",
            content=f"Memory {days_old} days old with {access_count} accesses",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            embedding=[0.1] * 384,
            provenance=provenance,
            access_count=access_count,
            ttl_seconds=None
        )
        
        tier = router.route(cube)
        assert tier == expected_tier
    
    def test_promote_from_cold_to_warm(self, router):
        """Test promoting a memory from cold to warm tier."""
        old_time = datetime.utcnow() - timedelta(days=15)
        provenance = Provenance.new("test", "session-1")
        provenance.created_at = old_time
        provenance.updated_at = old_time
        
        cube = MemCube(
            id="cold-to-promote",
            content="Cold memory to promote",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.COLD,
            embedding=[0.1] * 384,
            provenance=provenance,
            access_count=1,
            ttl_seconds=None
        )
        
        new_tier = router.promote(cube)
        assert new_tier == MemoryTier.WARM
    
    def test_promote_from_warm_to_hot(self, router):
        """Test promoting a memory from warm to hot tier."""
        cube = MemCube(
            id="warm-to-promote",
            content="Warm memory to promote",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            embedding=[0.1] * 384,
            provenance=Provenance.new("test", "session-1"),
            access_count=15,  # High access count
            ttl_seconds=None
        )
        
        new_tier = router.promote(cube)
        assert new_tier == MemoryTier.HOT
    
    def test_promote_hot_stays_hot(self, router):
        """Test that hot tier memories stay hot when promoted."""
        cube = MemCube(
            id="already-hot",
            content="Already hot memory",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.HOT,
            embedding=[0.1] * 384,
            provenance=Provenance.new("test", "session-1"),
            access_count=20,
            ttl_seconds=None
        )
        
        new_tier = router.promote(cube)
        assert new_tier == MemoryTier.HOT
    
    def test_demote_from_hot_to_warm(self, router):
        """Test demoting a memory from hot to warm tier."""
        old_time = datetime.utcnow() - timedelta(days=10)
        provenance = Provenance.new("test", "session-1")
        provenance.created_at = old_time
        provenance.updated_at = old_time
        
        cube = MemCube(
            id="hot-to-demote",
            content="Hot memory to demote",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.HOT,
            embedding=[0.1] * 384,
            provenance=provenance,
            access_count=2,  # Low access for hot tier
            ttl_seconds=None
        )
        
        new_tier = router.demote(cube)
        assert new_tier == MemoryTier.WARM
    
    def test_demote_from_warm_to_cold(self, router):
        """Test demoting a memory from warm to cold tier."""
        old_time = datetime.utcnow() - timedelta(days=20)
        provenance = Provenance.new("test", "session-1")
        provenance.created_at = old_time
        provenance.updated_at = old_time
        
        cube = MemCube(
            id="warm-to-demote",
            content="Warm memory to demote",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.WARM,
            embedding=[0.1] * 384,
            provenance=provenance,
            access_count=0,  # No access -> COLD per spec
            ttl_seconds=None
        )
        
        new_tier = router.demote(cube)
        assert new_tier == MemoryTier.COLD
    
    def test_demote_cold_stays_cold(self, router):
        """Test that cold tier memories stay cold when demoted."""
        cube = MemCube(
            id="already-cold",
            content="Already cold memory",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.COLD,
            embedding=[0.1] * 384,
            provenance=Provenance.new("test", "session-1"),
            access_count=0,
            ttl_seconds=None
        )
        
        new_tier = router.demote(cube)
        assert new_tier == MemoryTier.COLD

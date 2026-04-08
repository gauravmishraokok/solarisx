"""TierRouter implements memory tier routing logic.

Decides which tier (hot/warm/cold) a memory should be placed in based on
access patterns, recency, and business rules.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from memora.core.types import MemCube, MemoryTier
from memora.core.config import get_settings


class TierRouter:
    """Routes memories to appropriate tiers based on usage patterns."""
    
    def __init__(self):
        self.settings = get_settings()
    
    def route(self, cube: MemCube, current_time: datetime = None) -> MemoryTier:
        """
        Determine the appropriate tier for a memory cube.
        
        Args:
            cube: The memory cube to route
            current_time: Current timestamp (defaults to now)
            
        Returns:
            MemoryTier: The tier to place the memory in
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # IF access_count >= 10 AND last access within 24h -> HOT
        if self._should_be_hot(cube, current_time):
            return MemoryTier.HOT
        
        # ELIF access_count >= 1 OR created within 7 days -> WARM
        if self._should_be_warm(cube, current_time):
            return MemoryTier.WARM
        
        # ELSE -> COLD
        return MemoryTier.COLD
    
    def _should_be_hot(self, cube: MemCube, current_time: datetime) -> bool:
        """Check if memory should be in hot tier."""
        if cube.provenance:
            # IF access_count >= 10 AND last access within 24h -> HOT
            last_access_age = (current_time - cube.provenance.updated_at).total_seconds()
            hours_since_last_access = last_access_age / 3600
            
            if cube.access_count >= 10 and hours_since_last_access < 24:
                return True
        
        return False
    
    def _should_be_warm(self, cube: MemCube, current_time: datetime) -> bool:
        """Check if memory should be in warm tier."""
        if cube.provenance:
            creation_age = (current_time - cube.provenance.created_at).total_seconds()
            days_old = creation_age / (24 * 3600)
            
            # ELIF access_count >= 1 OR created within 7 days -> WARM
            if cube.access_count >= 1 or days_old < 7:
                return True
        
        return False
    
    def promote(self, cube: MemCube, current_time: datetime = None) -> MemoryTier:
        """
        Promote a memory to a higher tier based on recent access.
        Used when memory is accessed and needs to be moved up.
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        
        current_tier = cube.tier
        
        # Can't promote from hot (already highest)
        if current_tier == MemoryTier.HOT:
            return MemoryTier.HOT
        
        # Check if should be hot
        if self._should_be_hot(cube, current_time):
            return MemoryTier.HOT
        
        # Promote from cold to warm
        if current_tier == MemoryTier.COLD:
            return MemoryTier.WARM
        
        # Already warm, check if should stay warm
        return MemoryTier.WARM
    
    def demote(self, cube: MemCube, current_time: datetime = None) -> MemoryTier:
        """
        Demote a memory to a lower tier based on inactivity.
        Used during periodic cleanup or when storage is needed.
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        
        current_tier = cube.tier
        
        # Can't demote from cold (already lowest)
        if current_tier == MemoryTier.COLD:
            return MemoryTier.COLD
        
        # Check if should be cold using the same decision logic
        if not self._should_be_hot(cube, current_time) and not self._should_be_warm(cube, current_time):
            return MemoryTier.COLD
        
        # Demote from hot to warm
        if current_tier == MemoryTier.HOT:
            return MemoryTier.WARM
        
        # Already warm, check if should stay warm
        return MemoryTier.WARM
    
    def get_routing_stats(self, cubes: list[MemCube]) -> Dict[str, Any]:
        """
        Get statistics about memory distribution across tiers.
        Useful for monitoring and optimization.
        """
        total = len(cubes)
        if total == 0:
            return {
                "total_memories": 0,
                "hot_count": 0,
                "warm_count": 0,
                "cold_count": 0,
                "hot_percentage": 0.0,
                "warm_percentage": 0.0,
                "cold_percentage": 0.0
            }
        
        hot_count = sum(1 for cube in cubes if cube.tier == MemoryTier.HOT)
        warm_count = sum(1 for cube in cubes if cube.tier == MemoryTier.WARM)
        cold_count = sum(1 for cube in cubes if cube.tier == MemoryTier.COLD)
        
        return {
            "total_memories": total,
            "hot_count": hot_count,
            "warm_count": warm_count,
            "cold_count": cold_count,
            "hot_percentage": (hot_count / total) * 100,
            "warm_percentage": (warm_count / total) * 100,
            "cold_percentage": (cold_count / total) * 100
        }
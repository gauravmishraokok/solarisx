"""TTLManager manages memory lifecycle and expiration.

Handles TTL-based cleanup, tier migration, and memory expiration.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from memora.core.types import MemCube, MemoryTier
from memora.core.config import get_settings


class TTLManager:
    """Manages memory TTL and automatic cleanup operations."""
    
    def __init__(self):
        self.settings = get_settings()
    
    def is_expired(self, cube: MemCube, current_time: datetime = None) -> bool:
        """
        Check if a memory cube has expired based on its TTL.
        
        Args:
            cube: The memory cube to check
            current_time: Current timestamp (defaults to now)
            
        Returns:
            bool: True if the memory has expired
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # No TTL means never expires
        if not cube.ttl_seconds:
            return False
        
        # Check if last access was within TTL
        if cube.provenance and cube.provenance.updated_at:
            age_seconds = (current_time - cube.provenance.updated_at).total_seconds()
            return age_seconds > cube.ttl_seconds
        
        # Fall back to creation time
        if cube.provenance and cube.provenance.created_at:
            age_seconds = (current_time - cube.provenance.created_at).total_seconds()
            return age_seconds > cube.ttl_seconds
        
        return False
    
    def get_expiration_time(self, cube: MemCube) -> Optional[datetime]:
        """
        Get the exact expiration time for a memory cube.
        Returns None if memory has no TTL.
        """
        if not cube.ttl_seconds:
            return None
        
        # Use last access time if available
        if cube.provenance and cube.provenance.updated_at:
            return cube.provenance.updated_at + timedelta(seconds=cube.ttl_seconds)
        
        # Fall back to creation time
        if cube.provenance and cube.provenance.created_at:
            return cube.provenance.created_at + timedelta(seconds=cube.ttl_seconds)
        
        return None
    
    def extend_ttl(self, cube: MemCube, additional_seconds: int) -> MemCube:
        """
        Extend the TTL of a memory cube.
        Returns a new MemCube with extended TTL.
        """
        new_ttl = (cube.ttl_seconds or 0) + additional_seconds
        return cube.with_extra({**cube.extra, "ttl_seconds": new_ttl})
    
    def set_ttl(self, cube: MemCube, ttl_seconds: int) -> MemCube:
        """
        Set a specific TTL for a memory cube.
        Returns a new MemCube with the specified TTL.
        """
        return cube.with_extra({**cube.extra, "ttl_seconds": ttl_seconds})
    
    def get_expired_memories(self, cubes: List[MemCube], 
                           current_time: datetime = None) -> List[MemCube]:
        """
        Get all expired memories from a list.
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        
        expired = []
        for cube in cubes:
            if self.is_expired(cube, current_time):
                expired.append(cube)
        
        return expired
    
    def get_expiring_soon(self, cubes: List[MemCube], 
                         hours_ahead: int = 24) -> List[Dict[str, Any]]:
        """
        Get memories that will expire within the specified hours.
        Returns list of dicts with memory and expiration time.
        """
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        future_time = current_time + timedelta(hours=hours_ahead)
        
        expiring_soon = []
        for cube in cubes:
            expiration_time = self.get_expiration_time(cube)
            if expiration_time and expiration_time <= future_time:
                expiring_soon.append({
                    "cube": cube,
                    "expiration_time": expiration_time,
                    "hours_until_expiration": (expiration_time - current_time).total_seconds() / 3600
                })
        
        # Sort by expiration time (soonest first)
        expiring_soon.sort(key=lambda x: x["expiration_time"])
        return expiring_soon
    
    def auto_cleanup_expired(self, cubes: List[MemCube]) -> List[str]:
        """
        Automatically clean up expired memories.
        Returns list of expired memory IDs that should be deleted.
        """
        expired = self.get_expired_memories(cubes)
        return [cube.id for cube in expired]
    
    def get_ttl_stats(self, cubes: List[MemCube]) -> Dict[str, Any]:
        """
        Get statistics about TTL usage across memories.
        """
        total = len(cubes)
        if total == 0:
            return {
                "total_memories": 0,
                "with_ttl": 0,
                "without_ttl": 0,
                "expired": 0,
                "expiring_24h": 0,
                "expiring_7d": 0,
                "avg_ttl_hours": 0.0
            }
        
        with_ttl = [cube for cube in cubes if cube.ttl_seconds]
        without_ttl = [cube for cube in cubes if not cube.ttl_seconds]
        expired = self.get_expired_memories(cubes)
        expiring_24h = self.get_expiring_soon(cubes, hours_ahead=24)
        expiring_7d = self.get_expiring_soon(cubes, hours_ahead=168)  # 7 days
        
        avg_ttl_seconds = 0
        if with_ttl:
            avg_ttl_seconds = sum(cube.ttl_seconds for cube in with_ttl) / len(with_ttl)
        
        return {
            "total_memories": total,
            "with_ttl": len(with_ttl),
            "without_ttl": len(without_ttl),
            "expired": len(expired),
            "expiring_24h": len(expiring_24h),
            "expiring_7d": len(expiring_7d),
            "avg_ttl_hours": avg_ttl_seconds / 3600
        }
    
    def suggest_ttl_for_memory_type(self, memory_type: str, 
                                   access_pattern: str = "normal") -> int:
        """
        Suggest appropriate TTL based on memory type and access pattern.
        """
        base_ttls = {
            "episodic": {
                "high": self.settings.hot_tier_ttl_seconds,      # 24 hours
                "normal": self.settings.hot_tier_ttl_seconds * 3,  # 3 days
                "low": self.settings.hot_tier_ttl_seconds * 7    # 7 days
            },
            "semantic": {
                "high": self.settings.hot_tier_ttl_seconds * 30,  # 30 days
                "normal": self.settings.hot_tier_ttl_seconds * 90,  # 90 days
                "low": self.settings.hot_tier_ttl_seconds * 365   # 1 year
            },
            "kg_node": {
                "high": self.settings.hot_tier_ttl_seconds * 90,  # 90 days
                "normal": self.settings.hot_tier_ttl_seconds * 365, # 1 year
                "low": 0  # Never expires
            },
            "kg_edge": {
                "high": self.settings.hot_tier_ttl_seconds * 30,  # 30 days
                "normal": self.settings.hot_tier_ttl_seconds * 90,  # 90 days
                "low": self.settings.hot_tier_ttl_seconds * 365   # 1 year
            }
        }
        
        return base_ttls.get(memory_type, {}).get(access_pattern, 
                                                self.settings.hot_tier_ttl_seconds)
    
    def apply_tier_based_ttl(self, cube: MemCube) -> MemCube:
        """
        Apply appropriate TTL based on memory tier.
        Hot memories get shorter TTL, cold memories get longer TTL.
        """
        if cube.ttl_seconds:  # Don't override existing TTL
            return cube
        
        tier_ttls = {
            MemoryTier.HOT: self.settings.hot_tier_ttl_seconds,      # 24 hours
            MemoryTier.WARM: self.settings.hot_tier_ttl_seconds * 7,  # 7 days
            MemoryTier.COLD: 0  # Never expires
        }
        
        suggested_ttl = tier_ttls.get(cube.tier, 0)
        return self.set_ttl(cube, suggested_ttl)
    
    def schedule_cleanup(self, cleanup_interval_hours: int = 24) -> Dict[str, Any]:
        """
        Schedule periodic cleanup of expired memories.
        Returns cleanup schedule information.
        """
        return {
            "cleanup_interval_hours": cleanup_interval_hours,
            "next_cleanup": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=cleanup_interval_hours),
            "recommended_cleanup_times": [
                "02:00 UTC",  # 2 AM UTC (low traffic)
                "14:00 UTC"   # 2 PM UTC (backup cleanup)
            ]
        }
    
    def cleanup_expired_by_tier(self, cubes: List[MemCube]) -> Dict[MemoryTier, List[str]]:
        """
        Group expired memories by tier for targeted cleanup.
        """
        expired = self.get_expired_memories(cubes)
        
        expired_by_tier = {
            MemoryTier.HOT: [],
            MemoryTier.WARM: [],
            MemoryTier.COLD: []
        }
        
        for cube in expired:
            expired_by_tier[cube.tier].append(cube.id)
        
        return expired_by_tier
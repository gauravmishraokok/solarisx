from datetime import datetime
from memora.core.interfaces import IFailureLog

class ExperienceLearner:
    def __init__(self, failure_log: IFailureLog):
        self.failure_log = failure_log
        self._cache: dict[str, int] = {}
        self._cache_ttl: datetime | None = None

    async def get_penalized_ids(self) -> set[str]:
        """Fetches and caches specific MemoryCube IDs that must be penalized for 60 seconds."""
        now = datetime.utcnow()
        if self._cache_ttl and (now - self._cache_ttl).total_seconds() < 60:
            return {cid for cid, count in self._cache.items() if count >= 2}

        patterns = await self.failure_log.get_patterns()
        self._cache.clear()
        
        for pattern in patterns:
            if "cube_id" in pattern:
                self._cache[pattern["cube_id"]] = pattern.get("failure_count", 0)
            elif "memory_cluster_ids" in pattern:
                count = pattern.get("failure_count", 0)
                for cid in pattern["memory_cluster_ids"]:
                    self._cache[cid] = self._cache.get(cid, 0) + count

        self._cache_ttl = now
        return {cid for cid, count in self._cache.items() if count >= 2}

"""Provenance tracking and versioning utilities.

Manages memory provenance, version history, and parent-child relationships.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import uuid4
from memora.core.types import Provenance, MemCube
from memora.core.errors import ValidationError


class ProvenanceTracker:
    """Tracks and manages memory provenance and versioning."""
    
    def __init__(self):
        self._version_cache: Dict[str, int] = {}
    
    def create_new(self, origin: str, session_id: str) -> Provenance:
        """Create a new provenance record."""
        return Provenance.new(origin, session_id)
    
    def create_version(self, old_provenance: Provenance, 
                      origin: str = None, session_id: str = None) -> Provenance:
        """Create a new version of existing memory."""
        new_version = old_provenance.version + 1
        new_origin = origin or old_provenance.origin
        new_session_id = session_id or old_provenance.session_id
        
        return Provenance(
            origin=new_origin,
            session_id=new_session_id,
            created_at=old_provenance.created_at,  # Keep original creation time
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            version=new_version,
            parent_id=old_provenance.parent_id
        )
    
    def create_child(self, parent_provenance: Provenance, 
                    origin: str, session_id: str) -> Provenance:
        """Create a child memory with proper parent reference."""
        return self.create_version(parent_provenance, origin, session_id)
    
    def get_version_history(self, cube: MemCube) -> List[Dict[str, Any]]:
        """
        Get version history for a memory cube.
        In a real implementation, this would query the database.
        For now, returns a mock structure.
        """
        if not cube.provenance:
            return []
        
        return [
            {
                "version": cube.provenance.version,
                "created_at": cube.provenance.created_at,
                "updated_at": cube.provenance.updated_at,
                "origin": cube.provenance.origin,
                "session_id": cube.provenance.session_id
            }
        ]
    
    def find_root(self, provenance: Provenance) -> str:
        """Find the root memory ID in the provenance chain."""
        current_id = provenance.id
        # In a real implementation, this would traverse parent relationships
        # For now, return the current ID as root
        return current_id
    
    def validate_provenance(self, provenance: Provenance) -> None:
        """Validate provenance record for consistency."""
        if not provenance.origin:
            raise ValidationError("Provenance origin cannot be empty")
        
        if not provenance.session_id:
            raise ValidationError("Provenance session_id cannot be empty")
        
        if provenance.version < 1:
            raise ValidationError("Provenance version must be >= 1")
        
        if provenance.updated_at < provenance.created_at:
            raise ValidationError("Provenance updated_at cannot be before created_at")
        
        if provenance.parent_id == provenance.id:
            raise ValidationError("Provenance cannot be its own parent")
    
    def merge_provenance(self, primary: Provenance, secondary: Provenance,
                        origin: str, session_id: str) -> Provenance:
        """
        Create provenance for merged memory.
        Uses the oldest creation time and highest version number.
        """
        oldest_created = min(primary.created_at, secondary.created_at)
        highest_version = max(primary.version, secondary.version)
        
        return Provenance(
            origin=origin,
            session_id=session_id,
            created_at=oldest_created,
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            version=highest_version + 1,  # Increment for merge
            parent_id=primary.parent_id or secondary.parent_id
        )
    
    def get_session_memories(self, session_id: str) -> List[str]:
        """
        Get all memory IDs for a session.
        In a real implementation, this would query the database.
        """
        # Mock implementation - would query database in real system
        return []
    
    def get_memory_lineage(self, cube: MemCube) -> Dict[str, Any]:
        """
        Get complete lineage information for a memory.
        Returns parents, children, and siblings.
        """
        if not cube.provenance:
            return {
                "parent_id": None,
                "children": [],
                "siblings": [],
                "root_id": None
            }
        
        # Mock implementation - would query relationships in real system
        return {
            "parent_id": cube.provenance.parent_id,
            "children": [],  # Would query for children
            "siblings": [],   # Would query for siblings
            "root_id": self.find_root(cube.provenance)
        }
    
    def is_descendant(self, ancestor_id: str, descendant_id: str) -> bool:
        """
        Check if one memory is a descendant of another.
        In a real implementation, this would traverse the provenance tree.
        """
        # Mock implementation - would traverse tree in real system
        return False
    
    def get_branch_depth(self, cube: MemCube) -> int:
        """
        Get the depth of this memory in the provenance tree.
        Root memories have depth 0, children depth 1, etc.
        """
        if not cube.provenance or not cube.provenance.parent_id:
            return 0
        
        # Mock implementation - would traverse up the tree in real system
        return 1
    
    def prune_old_versions(self, max_versions: int = 10) -> List[str]:
        """
        Prune old versions of memories, keeping only the most recent.
        Returns list of pruned memory IDs.
        """
        # Mock implementation - would query and prune in real system
        return []
    
    def export_provenance_graph(self, session_id: str = None) -> Dict[str, Any]:
        """
        Export provenance relationships as a graph structure.
        Useful for visualization and analysis.
        """
        # Mock implementation - would build actual graph in real system
        return {
            "nodes": [],
            "edges": [],
            "metadata": {
                "exported_at": datetime.now(timezone.utc).replace(tzinfo=None),
                "session_id": session_id
            }
        }
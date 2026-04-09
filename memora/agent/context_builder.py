from memora.core.types import MemCube
from memora.core.config import Settings
from memora.retrieval.context_pager import ContextPager

class ContextBuilder:
    def __init__(self, context_pager: ContextPager, settings: Settings):
        self.context_pager = context_pager
        self.settings = settings

    async def build(self, session_id: str, retrieved: list[MemCube], base_system_prompt: str) -> str:
        # Pager assumes you pass `current_token_count`. SessionManager should track this? 
        # Actually the spec says "active_memories = await context_pager.build_context(retrieved, current_token_count)".
        # Wait, the spec for ContextBuilder `__init__` does not get `session_manager`. 
        # I will parse the active_memories with a default or 0 current token count if not passed. 
        # Let's import the session state later if needed. The Spec says:
        # active_memories = await context_pager.build_context(retrieved, current_token_count)
        # I'll default `current_token_count` to 0 for now as it's not strictly passed in `build` args.
        
        active_memories = await self.context_pager.build_context(retrieved, 0)
        
        if not active_memories:
            return base_system_prompt
            
        memory_block = self.format_memories(active_memories)
        
        return f"{base_system_prompt}\n\n<RELEVANT MEMORIES — internal context only, do NOT reproduce in your response>\n{memory_block}\n</RELEVANT MEMORIES>"

    def format_memories(self, memories: list[MemCube]) -> str:
        formatted_blocks = []
        for mem in memories:
            tags_str = ", ".join(mem.tags)
            updated_at = mem.provenance.updated_at.isoformat() if mem.provenance else "Unknown"
            block = f"[{mem.memory_type.value}] {mem.content}\nTags: {tags_str}\nLast updated: {updated_at}\n---"
            formatted_blocks.append(block)
            
        return "\n".join(formatted_blocks)

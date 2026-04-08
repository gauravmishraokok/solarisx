"""SentenceTransformerEmbedder implements IEmbeddingModel.

Uses sentence-transformers all-MiniLM-L6-v2 to produce 384-dim embeddings.
"""

from typing import List
import asyncio
from sentence_transformers import SentenceTransformer
from memora.core.interfaces import IEmbeddingModel
from memora.core.errors import EmbeddingDimensionError


class SentenceTransformerEmbedder(IEmbeddingModel):
    """Concrete embedder using sentence-transformers."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self._dim = len(self.model.encode("test"))
    
    async def embed(self, text: str) -> List[float]:
        """Return 384-dim embedding for text."""
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None, self.model.encode, text
        )
        result = embedding.tolist()
        if len(result) != 384:
            raise EmbeddingDimensionError(expected=384, got=len(result))
        return result
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Return batch of embeddings. More efficient than calling embed() in a loop."""
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, self.model.encode, texts
        )
        result = [emb.tolist() for emb in embeddings]
        for emb in result:
            if len(emb) != 384:
                raise EmbeddingDimensionError(expected=384, got=len(emb))
        return result
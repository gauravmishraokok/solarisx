"""Single source of truth for all configuration.

Reads from environment variables and .env file.
"""

from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import Optional, Literal


class Settings(BaseSettings):
    # LLM providers
    groq_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = "groq"     # "groq" | "openai"
    llm_model: str = "llama3-70b-8192"  # Model string

    # Databases
    database_url: str = "postgresql+asyncpg://memora:memora@localhost:5432/memora"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "memorapass"
    redis_url: str = "redis://localhost:6379"
    use_networkx_fallback: bool = False  # Use NetworkX instead of Neo4j (demo/offline mode)

    # Memory Court
    contradiction_threshold: float = Field(default=0.75, ge=0.0, le=1.0)   # [0.0, 1.0]
    court_retrieval_top_k: int = 3           # How many existing memories to check against

    # Retrieval
    top_k_retrieval: int = 5
    context_window_budget: int = 8000        # tokens before MemGPT pager evicts
    dense_weight: float = Field(default=0.7, ge=0.0, le=1.0)                # Weight for dense score in hybrid fusion
    symbolic_weight: float = Field(default=0.3, ge=0.0, le=1.0)             # Weight for symbolic score in hybrid fusion
    failure_penalty: float = 0.4             # Score multiplier for known-bad memory clusters

    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: Literal[384] = 384  # The all-MiniLM-L6-v2 output dimension

    # Episode segmentation
    episode_buffer_size: int = 5             # Max turns before forced episode boundary
    boundary_threshold: float = Field(default=0.4, ge=0.0, le=1.0)          # Semantic shift score to trigger boundary

    # TTL
    hot_tier_ttl_seconds: int = 86400        # 24h
    cold_tier_threshold_days: int = 7        # Move to cold after 7 days no access
    
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @field_validator('dense_weight', mode='before')
    @classmethod
    def validate_weights_sum(cls, v, info):
        """Ensure dense_weight + symbolic_weight equals 1.0."""
        values = info.data if info.data else {}
        if 'dense_weight' in values and 'symbolic_weight' in values:
            dense = values['dense_weight']
            symbolic = values['symbolic_weight']
            if abs((dense + symbolic) - 1.0) > 0.001:
                raise ValueError('dense_weight + symbolic_weight must equal 1.0')
        return v

    @field_validator('contradiction_threshold', mode='before')
    @classmethod
    def validate_contradiction_threshold(cls, v):
        """Validate contradiction_threshold is in valid range."""
        if not (0.0 <= v <= 1.0):
            raise ValueError('contradiction_threshold must be between 0.0 and 1.0')
        return v


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance. Tests override via environment variables."""
    return Settings()
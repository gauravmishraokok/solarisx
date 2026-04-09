import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta
from memora.core.types import MemCube, MemoryType, Provenance
from memora.core.config import Settings
from memora.retrieval.dense_retriever import DenseRetriever
from memora.retrieval.symbolic_retriever import SymbolicRetriever
from memora.retrieval.query_expander import QueryExpander
from memora.retrieval.reranker import Reranker
from memora.retrieval.experience_learner import ExperienceLearner
from memora.retrieval.hybrid_retriever import HybridRetriever
from memora.retrieval.context_pager import ContextPager, ContextSlot

@pytest.mark.asyncio
async def test_dense_search_returns_sorted_by_score(mock_vector_store, mock_embedder, cube_factory):
    # Prepopulate mock vector store
    for i in range(3):
        cube = await cube_factory(f"test content {i}")
        cube.id = f"mock-cube-{i}"
        await mock_vector_store.upsert(cube)

    retriever = DenseRetriever(mock_vector_store, mock_embedder)
    results = await retriever.search("test query")
    assert len(results) == 3
    assert results[0][0].id.startswith("mock-cube-")
    assert results[0][1] >= results[1][1]

@pytest.mark.asyncio
async def test_symbolic_search_by_tags(cube_factory, mock_db):
    cube1 = await cube_factory("cube 1")
    cube1.tags = ["pricing", "strategy"]

    from memora.storage.mongo.collections import MEM_CUBES
    from memora.storage.vector.mongo_vector_client import _cube_to_doc
    await mock_db[MEM_CUBES].insert_one(_cube_to_doc(cube1))

    retriever = SymbolicRetriever(mock_db)
    results = await retriever.search_by_tags(["pricing"])
    assert len(results) == 1
    assert results[0].tags == ["pricing", "strategy"]

@pytest.mark.asyncio
async def test_hybrid_merges_both_sources(mock_vector_store, mock_embedder, cube_factory, mock_failure_log):
    cube_A = await cube_factory("a")
    cube_A.id = "mock-cube-0"
    await mock_vector_store.upsert(cube_A)

    cube_B = await cube_factory("b")
    cube_B.id = "mock-cube-symbolic"

    dense = DenseRetriever(mock_vector_store, mock_embedder)

    symbolic = AsyncMock()
    symbolic.search_by_tags.return_value = [cube_B]

    kg_repo = AsyncMock()
    expander = QueryExpander(kg_repo, symbolic)

    settings = Settings(dense_weight=0.5, symbolic_weight=0.5, failure_penalty=0.5)
    learner = ExperienceLearner(mock_failure_log)
    reranker = Reranker(learner, settings)

    hybrid = HybridRetriever(dense, symbolic, expander, reranker, settings)
    results = await hybrid.search("query")

    ids = [c.id for c in results]
    assert "mock-cube-0" in ids
    assert "mock-cube-symbolic" in ids

@pytest.mark.asyncio
async def test_reranker_penalizes_failure_clusters(cube_factory, mock_failure_log):
    cube_X = await cube_factory("x")
    cube_X.id = "id1" # From mock_failure_log ("id1")
    cube_Y = await cube_factory("y")
    
    learner = ExperienceLearner(mock_failure_log)
    settings = Settings(dense_weight=1.0, symbolic_weight=0.0, failure_penalty=0.5)
    reranker = Reranker(learner, settings)
    
    dense_results = [(cube_X, 0.9), (cube_Y, 0.7)]
    ranked = await reranker.rerank(dense_results, [], "query")
    
    assert ranked[0].cube.id == cube_Y.id  # Y overtook X due to penalty
    assert ranked[1].cube.id == cube_X.id

@pytest.mark.asyncio
async def test_reranker_recency_boost(cube_factory, mock_failure_log):
    cube_OLD = await cube_factory("old")
    cube_OLD.provenance.updated_at = datetime.utcnow() - timedelta(days=30)
    cube_OLD.id = "old"
    
    cube_NEW = await cube_factory("new")
    cube_NEW.provenance.updated_at = datetime.utcnow()
    cube_NEW.id = "new"
    
    learner = ExperienceLearner(mock_failure_log)
    settings = Settings(dense_weight=1.0, symbolic_weight=0.0)
    reranker = Reranker(learner, settings)
    dense_results = [(cube_OLD, 0.8), (cube_NEW, 0.8)]
    ranked = await reranker.rerank(dense_results, [], "query")
    
    assert ranked[0].cube.id == cube_NEW.id

@pytest.mark.asyncio
async def test_context_pager_evicts_on_overflow(cube_factory):
    settings = Settings(context_window_budget=100)
    pager = ContextPager(settings)
    
    cubes = []
    for i in range(3):
        c = await cube_factory("x" * 200)
        c.id = str(i)
        cubes.append(c)
    
    result = await pager.build_context(cubes, 0)
    assert len(result) == 2

@pytest.mark.asyncio
async def test_context_pager_respects_priority_order(cube_factory):
    settings = Settings(context_window_budget=100)
    pager = ContextPager(settings)
    
    cubes = []
    for i in range(3):
        c = await cube_factory("x" * 200)
        c.id = str(i)
        c.provenance.session_id = str(i)
        cubes.append(c)
    
    pager._priority = lambda cube, score: float(cube.provenance.session_id)
    
    result = await pager.build_context(cubes, 0)
    ids = [c.provenance.session_id for c in result]
    assert "2" in ids
    assert "1" in ids
    assert "0" not in ids

@pytest.mark.asyncio
async def test_experience_learner_cache_freshness(mock_failure_log):
    learner = ExperienceLearner(mock_failure_log)
    assert await learner.get_penalized_ids() == {"id1", "id2"}
    
    mock_failure_log.get_patterns = AsyncMock(return_value=[])
    assert await learner.get_penalized_ids() == {"id1", "id2"}
    
    learner._cache_ttl = datetime.utcnow() - timedelta(seconds=65)
    
    assert await learner.get_penalized_ids() == set()

@pytest.mark.asyncio
async def test_query_expander_collects_tags(cube_factory):
    cube1 = await cube_factory("x")
    cube1.tags = ["pricing", "B2B"]
    cube2 = await cube_factory("x")
    cube2.tags = ["B2B", "enterprise"]
    
    symbolic = AsyncMock()
    symbolic.search_by_tags.return_value = [cube1, cube2]
    
    expander = QueryExpander(AsyncMock(), symbolic)
    result = await expander.expand("test", seed_tags=["pricing"])
    
    assert set(result.expanded_tags) == {"pricing", "B2B", "enterprise"}

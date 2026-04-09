"""FastAPI application entrypoint for MEMORA."""

from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI

from memora.api.middleware import register_error_handlers, register_middleware
from memora.api.routers import chat, court, graph, health, memories, timeline
from memora.core.config import get_settings
from memora.core.events import (
    bus, MemoryApproved, MemoryQuarantined, ResolutionApplied, NegativeOutcomeRecorded
)

# New Motor imports
from memora.storage.mongo.connection import init_motor, get_database, dispose_motor
from memora.storage.mongo.collections import setup_indexes
from memora.storage.vector.mongo_vector_client import MongoVectorClient

# Embedding & Graph
from memora.storage.vector.embedding import SentenceTransformerEmbedder

# Vault
from memora.vault.timeline_writer import TimelineWriter
from memora.vault.mem_cube import MemCubeFactory
from memora.vault.episodic_repo import EpisodicRepo
from memora.vault.semantic_repo import SemanticRepo
from memora.vault.kg_repo import KGRepo
from memora.vault.quarantine_repo import QuarantineRepo
from memora.vault.vault_event_writer import VaultEventWriter

# Experience & Retrieval
from memora.experience.failure_logger import FailureLogger
from memora.experience.outcome_tracker import OutcomeTracker
from memora.retrieval.experience_learner import ExperienceLearner
from memora.retrieval.dense_retriever import DenseRetriever
from memora.retrieval.symbolic_retriever import SymbolicRetriever
from memora.retrieval.query_expander import QueryExpander
from memora.retrieval.reranker import Reranker
from memora.retrieval.hybrid_retriever import HybridRetriever
from memora.retrieval.context_pager import ContextPager

# LLM
from memora.llm.groq_client import GroqClient

# Court
from memora.court.contradiction_detector import ContradictionDetector
from memora.court.judge_agent import JudgeAgent
from memora.court.quarantine_manager import QuarantineManager
from memora.court.resolution_handler import ResolutionHandler

# Scheduler
from memora.scheduler.boundary_detector import BoundaryDetector
from memora.scheduler.episode_segmenter import EpisodeSegmenter
from memora.scheduler.type_classifier import TypeClassifier
from memora.scheduler.predict_calibrate import PredictCalibrateLoop
from memora.scheduler.ingestion_pipeline import IngestionPipeline

# Agent
from memora.agent.session_manager import SessionManager
from memora.agent.context_builder import ContextBuilder
from memora.agent.tool_executor import ToolExecutor
from memora.agent.memora_agent import MemoraAgent


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # 1. MongoDB Atlas connection
    await init_motor(settings.mongodb_url, settings.mongodb_db_name)
    db = await get_database()
    await setup_indexes(db)         # Idempotent — safe to run every startup

    # 2. Embedding model
    embedder = SentenceTransformerEmbedder(settings.embedding_model)

    # 3. Storage clients
    mongo_vector_client = MongoVectorClient(db, settings.embedding_dim)

    # 4. Vault
    timeline_writer = TimelineWriter(db)                        # Motor-backed
    cube_factory = MemCubeFactory(embedder, settings)
    episodic_repo = EpisodicRepo(mongo_vector_client, timeline_writer)
    semantic_repo = SemanticRepo(mongo_vector_client, timeline_writer)
    kg_repo = KGRepo(timeline_writer)
    quarantine_repo = QuarantineRepo(db)                        # Motor-backed

    # 5. Retrieval
    failure_log = FailureLogger(db, bus)                        # Motor-backed
    experience_learner = ExperienceLearner(failure_log)
    dense = DenseRetriever(mongo_vector_client, embedder)
    symbolic = SymbolicRetriever(db)                            # Motor-backed
    expander = QueryExpander(kg_repo, symbolic)
    reranker = Reranker(experience_learner, settings)
    retriever = HybridRetriever(dense, symbolic, expander, reranker, settings)
    context_pager = ContextPager(settings)

    # 6. LLM
    llm = GroqClient(api_key=settings.groq_api_key, model=settings.llm_model)

    # 7. Court
    detector = ContradictionDetector(settings.contradiction_threshold)
    judge = JudgeAgent(llm, retriever, detector, settings)      # subscribes on init
    quarantine_mgr = QuarantineManager(quarantine_repo)
    resolution_handler = ResolutionHandler(quarantine_repo, bus)

    # 8. Scheduler
    boundary_detector = BoundaryDetector(embedder, settings)
    segmenter = EpisodeSegmenter(boundary_detector)
    classifier = TypeClassifier(llm)
    predict_calibrate = PredictCalibrateLoop(retriever, llm)
    pipeline = IngestionPipeline(
        segmenter, classifier, predict_calibrate, cube_factory, retriever, bus
    )

    # 9. Agent
    session_mgr = SessionManager()
    context_builder = ContextBuilder(context_pager, settings)
    outcome_tracker = OutcomeTracker()
    tool_executor = ToolExecutor(retriever, bus)
    agent = MemoraAgent(
        llm, retriever, context_builder, tool_executor,
        session_mgr, outcome_tracker, bus, settings
    )

    # 10. Wire vault event handlers — LAST
    vault_writer = VaultEventWriter(
        episodic_repo, semantic_repo, kg_repo, quarantine_repo, cube_factory
    )
    bus.subscribe(MemoryApproved,           vault_writer.handle_approved)
    bus.subscribe(MemoryQuarantined,        vault_writer.handle_quarantined)
    bus.subscribe(ResolutionApplied,        vault_writer.handle_resolution)
    bus.subscribe(NegativeOutcomeRecorded,  failure_log.handle)

    # 11. Store in app.state
    app.state.agent = agent
    app.state.retriever = retriever
    app.state.quarantine_mgr = quarantine_mgr
    app.state.resolution_handler = resolution_handler
    app.state.episodic_repo = episodic_repo
    app.state.semantic_repo = semantic_repo
    app.state.kg_repo = kg_repo
    app.state.settings = settings
    app.state.db = db
    app.state.cube_factory = cube_factory

    yield

    # Shutdown
    await context_pager.evict_all()
    await dispose_motor()           # Replaces dispose_engine()
    bus.clear()


def create_app() -> FastAPI:
    """Create configured FastAPI app."""
    app = FastAPI(
        title="MEMORA",
        description="Persistent Memory for Long-Running Agents",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_middleware(app)
    register_error_handlers(app)
    app.include_router(chat.router)
    app.include_router(memories.router)
    app.include_router(court.router)
    app.include_router(graph.router)
    app.include_router(timeline.router)
    app.include_router(health.router)
    return app


app = create_app()

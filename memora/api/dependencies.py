"""
api/dependencies.py

FastAPI dependency injection helpers for app.state services.
"""

from __future__ import annotations

from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from memora.agent.memora_agent import MemoraAgent
from memora.core.config import Settings
from memora.court.quarantine_manager import QuarantineManager
from memora.court.resolution_handler import ResolutionHandler
from memora.retrieval.hybrid_retriever import HybridRetriever
from memora.vault.episodic_repo import EpisodicRepo
from memora.vault.kg_repo import KGRepo
from memora.vault.mem_cube import MemCubeFactory
from memora.vault.semantic_repo import SemanticRepo


def get_agent(request: Request) -> MemoraAgent:
    return request.app.state.agent


def get_quarantine_manager(request: Request) -> QuarantineManager:
    return request.app.state.quarantine_mgr


def get_resolution_handler(request: Request) -> ResolutionHandler:
    return request.app.state.resolution_handler


def get_retriever(request: Request) -> HybridRetriever:
    return request.app.state.retriever


def get_episodic_repo(request: Request) -> EpisodicRepo:
    return request.app.state.episodic_repo


def get_semantic_repo(request: Request) -> SemanticRepo:
    return request.app.state.semantic_repo


def get_kg_repo(request: Request) -> KGRepo:
    return request.app.state.kg_repo


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> AsyncIOMotorDatabase:
    return request.app.state.db


def get_cube_factory(request: Request) -> MemCubeFactory:
    return request.app.state.cube_factory

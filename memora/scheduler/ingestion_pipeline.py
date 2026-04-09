from memora.core.events import EventBus, ConversationTurnEvent, MemoryWriteRequested
from memora.core.types import MemoryType, MemCube, Provenance, Episode
from memora.scheduler.episode_segmenter import EpisodeSegmenter
from memora.scheduler.type_classifier import TypeClassifier
from memora.scheduler.predict_calibrate import PredictCalibrateLoop
from memora.retrieval.hybrid_retriever import IRetriever
import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

class MemCubeFactory:
    def create(self, content: str, memory_type: MemoryType, session_id: str, tags: list[str], key: Optional[str] = None) -> MemCube:
        from memora.core.types import MemCube, Provenance

        cube = MemCube(
            id=str(uuid.uuid4()),
            content=content,
            memory_type=memory_type,
            tags=tags,
            provenance=Provenance.new("agent_inference", session_id)
        )
        if key:
            cube.extra["key"] = key
        return cube

class IngestionPipeline:
    """Orchestrates the conversion of ConversationTurnEvents into segmented, classified, and deduplicated MemCubes."""
    def __init__(
        self,
        segmenter: EpisodeSegmenter,
        classifier: TypeClassifier,
        predict_calibrate: PredictCalibrateLoop,
        cube_factory: MemCubeFactory,
        retriever: IRetriever,
        bus: EventBus,
    ):
        self.segmenter = segmenter
        self.classifier = classifier
        self.predict_calibrate = predict_calibrate
        self.cube_factory = cube_factory
        self.retriever = retriever
        self.bus = bus

        bus.subscribe(ConversationTurnEvent, self.handle)

    async def handle(self, event: ConversationTurnEvent) -> None:
        # ── Fast path: extract semantic facts from the user message IMMEDIATELY ──
        # This runs on every turn so name/identity claims are stored right away
        # and can be contradicted by the court in the same session without delay.
        await self._fast_semantic_pass(event.user_message, event.session_id)

        # ── Regular path: boundary-based episodic + semantic processing ──────────
        # Episodic memories still go through the segmenter for narrative grouping.
        # Semantic facts here act as a dedup check — find_gap will return
        # NO_NEW_INFORMATION if the fast-path already wrote the same fact.
        try:
            turn_text = f"User: {event.user_message}\nAssistant: {event.agent_response}"
            episode = await self.segmenter.process_turn(turn_text, event.session_id)

            if episode is None:
                return

            results = await self.classifier.classify(episode)

            for result in results:
                if result.memory_type == MemoryType.SEMANTIC:
                    retrieved = await self.retriever.search(result.content, top_k=3)
                    gap_text = await self.predict_calibrate.find_gap(episode, retrieved)
                    if gap_text is None:
                        continue
                    content = gap_text
                else:
                    content = result.content

                cube = self.cube_factory.create(
                    content=content,
                    memory_type=result.memory_type,
                    session_id=event.session_id,
                    tags=result.tags,
                    key=result.key
                )

                await self.bus.publish(MemoryWriteRequested(cube=cube, session_id=event.session_id))
        except Exception as e:
            logger.error(f"Ingestion pipeline (regular path) failed: {e}")

    async def _fast_semantic_pass(self, user_message: str, session_id: str) -> None:
        """
        Immediately extract SEMANTIC facts from the raw user message.

        Bypasses boundary detection so that identity claims (name, college, GitHub, etc.)
        enter the court and vault within the same conversational turn, enabling real-time
        contradiction detection.
        """
        try:
            # Wrap the user message alone as a minimal episode
            mini_episode = Episode(
                id=str(uuid.uuid4()),
                content=f"User: {user_message}",
                start_turn=0,
                end_turn=0,
                session_id=session_id,
                boundary_score=1.0,
            )

            results = await self.classifier.classify(mini_episode)

            for result in results:
                if result.memory_type != MemoryType.SEMANTIC:
                    continue  # Episodic memories still go through the regular path

                retrieved = await self.retriever.search(result.content, top_k=5)
                gap_text = await self.predict_calibrate.find_gap(mini_episode, retrieved)
                if gap_text is None:
                    continue  # Already known — skip to avoid duplicate

                cube = self.cube_factory.create(
                    content=gap_text,
                    memory_type=MemoryType.SEMANTIC,
                    session_id=session_id,
                    tags=result.tags,
                    key=result.key,
                )

                await self.bus.publish(MemoryWriteRequested(cube=cube, session_id=session_id))
        except Exception as e:
            logger.error(f"Fast semantic pass failed: {e}")

from memora.core.events import EventBus, ConversationTurnEvent, MemoryWriteRequested
from memora.core.types import MemoryType, MemCube, Provenance
from memora.scheduler.episode_segmenter import EpisodeSegmenter
from memora.scheduler.type_classifier import TypeClassifier
from memora.scheduler.predict_calibrate import PredictCalibrateLoop
from memora.retrieval.hybrid_retriever import IRetriever
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class MemCubeFactory:
    def create(self, content: str, memory_type: MemoryType, session_id: str, tags: list[str], key: Optional[str] = None) -> MemCube:
        from memora.core.types import MemCube, Provenance
        import uuid
        
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
            logger.error(f"Ingestion pipeline failed: {e}")

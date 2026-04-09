"""
court/judge_agent.py — The Memory Court Judge.

Responsibilities:
- Subscribe to MemoryWriteRequested
- Retrieve top-3 existing memories most similar to the candidate
- Call LLM (Groq) with a two-shot contradiction detection prompt
- Publish MemoryApproved or MemoryQuarantined

Key design: Court NEVER writes to DB. It only emits verdicts via events.
This means Court has zero dependency on vault/ or storage/.
Court only depends on: core/, llm/, retrieval/ (read-only).

Contradiction threshold: configurable in config.py (default: 0.75)
"""
from memora.core.events import bus, MemoryWriteRequested, MemoryApproved, MemoryQuarantined
from memora.core.types import ContradictionVerdict
from memora.core.config import Settings
from memora.core.interfaces import ILLM
from memora.llm.prompts.judge_prompts import JUDGE_SYSTEM_PROMPT
from memora.retrieval.hybrid_retriever import HybridRetriever
from .contradiction_detector import ContradictionDetector


class JudgeAgent:
    def __init__(
        self,
        llm: ILLM,
        retriever: HybridRetriever,
        detector: ContradictionDetector,
        settings: Settings,
    ):
        self.llm = llm
        self.retriever = retriever
        self.detector = detector
        self.settings = settings
        self.threshold = settings.contradiction_threshold
        bus.subscribe(MemoryWriteRequested, self._on_write_requested)

    async def _on_write_requested(self, event: MemoryWriteRequested) -> None:
        """
        1. Retrieve top-3 existing memories similar to candidate
        2. Run LLM contradiction check
        3. Publish approved or quarantined
        """
        try:
            candidates = await self.retriever.search(
                query=event.cube.content,
                top_k=self.settings.court_retrieval_top_k
            )
        except Exception as e:
            # Log error and fail open
            await bus.publish(MemoryApproved(cube=event.cube))
            return

        if not candidates:
            await bus.publish(MemoryApproved(cube=event.cube, related_cubes=[]))
            return

        verdicts = []
        for candidate in candidates:
            try:
                user_msg = f"INCOMING:\n{event.cube.content}\n\nEXISTING:\n{candidate.content}"
                schema = {
                    "contradiction_score": 0.0,
                    "reasoning": "",
                    "suggested_resolution": ""
                }
                resp_json = await self.llm.complete_json(
                    system=JUDGE_SYSTEM_PROMPT,
                    user=user_msg,
                    schema=schema
                )

                score = self.detector.score_from_llm_response(resp_json)
                verdict = self.detector.make_verdict(
                    incoming_id=event.cube.id,
                    conflicting_id=candidate.id,
                    score=score,
                    reasoning=resp_json["reasoning"],
                    suggested_resolution=resp_json.get("suggested_resolution")
                )
                verdicts.append(verdict)
            except Exception as e:
                # Log error, continue testing other candidates
                pass

        if not verdicts:
            await bus.publish(MemoryApproved(cube=event.cube, related_cubes=candidates))
            return

        max_verdict = max(verdicts, key=lambda v: v.score)

        if max_verdict.is_quarantined:
            await bus.publish(MemoryQuarantined(verdict=max_verdict, incoming_cube=event.cube))
        else:
            await bus.publish(MemoryApproved(cube=event.cube, related_cubes=candidates))

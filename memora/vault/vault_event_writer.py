"""
vault/vault_event_writer.py

Subscribes to Court events and writes approved/resolved memories to vault.
This is the ONLY place that bridges the event bus to vault storage.
Court emits events. This class listens and persists.
"""
from memora.core.events import MemoryApproved, MemoryQuarantined, ResolutionApplied
from memora.core.types import MemoryType, QuarantineStatus
from memora.vault.episodic_repo import EpisodicRepo
from memora.vault.semantic_repo import SemanticRepo
from memora.vault.kg_repo import KGRepo
from memora.vault.quarantine_repo import QuarantineRepo
from memora.vault.mem_cube import MemCubeFactory


class VaultEventWriter:
    def __init__(
        self,
        episodic_repo: EpisodicRepo,
        semantic_repo: SemanticRepo,
        kg_repo: KGRepo,
        quarantine_repo: QuarantineRepo,
        cube_factory: MemCubeFactory,
    ):
        self.episodic = episodic_repo
        self.semantic = semantic_repo
        self.kg = kg_repo
        self.quarantine = quarantine_repo
        self.factory = cube_factory

    async def handle_approved(self, event: MemoryApproved) -> None:
        """
        Route approved MemCube to the correct repo based on memory_type.
        EPISODIC  → episodic_repo.save()
        SEMANTIC  → semantic_repo.upsert_by_key()
        KG_NODE   → kg_repo.upsert_node()

        All approved memories are ALSO added as KG nodes and linked to related
        memories found during court evaluation (multi-link knowledge graph).
        """
        cube = event.cube
        try:
            if cube.memory_type == MemoryType.EPISODIC:
                await self.episodic.save(cube)
            elif cube.memory_type == MemoryType.SEMANTIC:
                key = cube.extra.get("key", cube.id)
                await self.semantic.upsert_by_key(key, cube)
            elif cube.memory_type == MemoryType.KG_NODE:
                await self.kg.upsert_node(cube)
        except Exception as e:
            # Log and continue — never crash the event loop
            print(f"[VaultEventWriter] handle_approved failed (primary store): {e}")
            return

        # ── Knowledge Graph: add every approved memory as a node ──────────────
        # This makes the KG a full-fidelity graph of ALL memories, not just KG_NODE types.
        try:
            await self.kg.upsert_node(cube)
        except Exception as e:
            print(f"[VaultEventWriter] KG upsert_node failed for {cube.id}: {e}")
            return

        # ── Knowledge Graph: link new node to all related memories ────────────
        # related_cubes are the similar memories retrieved during court evaluation.
        # Each one gets a bidirectional "relates_to" edge so the graph is multi-linked.
        for related in event.related_cubes:
            if related.id == cube.id:
                continue
            try:
                # Ensure the related node exists in the KG (upsert is idempotent)
                await self.kg.upsert_node(related)
                # Forward edge: new memory → related memory
                await self.kg.add_edge(
                    from_id=cube.id,
                    to_id=related.id,
                    label="relates_to",
                    metadata={"origin": cube.memory_type.value}
                )
                # Back edge: related memory → new memory
                await self.kg.add_edge(
                    from_id=related.id,
                    to_id=cube.id,
                    label="relates_to",
                    metadata={"origin": related.memory_type.value}
                )
            except Exception as e:
                print(f"[VaultEventWriter] KG edge creation failed ({cube.id} ↔ {related.id}): {e}")

    async def handle_quarantined(self, event: MemoryQuarantined) -> None:
        """
        Save incoming cube + verdict to quarantine_repo as PENDING.
        """
        try:
            await self.quarantine.save_pending(event.incoming_cube, event.verdict)
        except Exception as e:
            print(f"[VaultEventWriter] handle_quarantined failed: {e}")

    async def handle_resolution(self, event: ResolutionApplied) -> None:
        """
        On RESOLVED_ACCEPT: fetch original cube from quarantine, write to vault.
        On RESOLVED_MERGE:  create new cube with merged_content, write to vault.
        On RESOLVED_REJECT: no write needed, quarantine record already updated.
        """
        try:
            record = await self.quarantine.get(event.quarantine_id)
            if not record:
                return

            if event.resolution == QuarantineStatus.RESOLVED_ACCEPT:
                cube = self.factory.from_db_row(record["incoming_cube_json"])
                await self._route_cube(cube)

            elif event.resolution == QuarantineStatus.RESOLVED_MERGE:
                original = self.factory.from_db_row(record["incoming_cube_json"])
                merged_cube = await self.factory.create(
                    content=event.merged_content,
                    memory_type=original.memory_type,
                    session_id=event.session_id,
                    origin="resolution",
                    tags=original.tags,
                    extra=original.extra,
                )
                await self._route_cube(merged_cube)

            # RESOLVED_REJECT: do nothing — memory is discarded

        except Exception as e:
            print(f"[VaultEventWriter] handle_resolution failed: {e}")

    async def _route_cube(self, cube) -> None:
        """Internal helper: route a MemCube to the correct vault repo."""
        if cube.memory_type == MemoryType.EPISODIC:
            await self.episodic.save(cube)
        elif cube.memory_type == MemoryType.SEMANTIC:
            key = cube.extra.get("key", cube.id)
            await self.semantic.upsert_by_key(key, cube)
        elif cube.memory_type == MemoryType.KG_NODE:
            await self.kg.upsert_node(cube)

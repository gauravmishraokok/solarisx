"""Extract compact episodic, semantic, and KG memories from a chat turn."""

from __future__ import annotations

import hashlib
import re

from memora.core.interfaces import ILLM

DISTILL_SCHEMA = {
    "episodic_line": "",
    "semantic_facts": [],
    "kg_entities": [],
}

SYSTEM = """You turn one chat turn into structured memory for a personal AI assistant.
Return JSON with exactly these keys:
- episodic_line: string — one short sentence (max 28 words) about what happened or was discussed in this turn from the user's perspective, or "" if nothing worth remembering as an event.
- semantic_facts: array of up to 3 strings — short standalone facts (max 18 words each). No dialogue, no "User said". Empty array if none.
- kg_entities: array of up to 3 objects, each {"title": "...", "detail": "..."}. title must be 3–6 words in Title Case (like a short note heading, e.g. "Tea And Coffee Preference"). detail is one clarifying sentence or "". Skip entities that add nothing new.

Rules: Never paste the full user or assistant messages. Be concise. If the turn is trivial, use "" and []."""


def _fallback_distill(user_message: str, assistant_message: str) -> dict:
    """Cheap heuristic when the LLM is unavailable."""
    u = (user_message or "").strip()
    a = (assistant_message or "").strip()
    episodic = ""
    if u:
        episodic = u.split("\n")[0].strip()
        if len(episodic) > 160:
            episodic = episodic[:157].rstrip() + "…"
    semantic: list[str] = []
    if a:
        first = re.split(r"(?<=[.!?])\s+", a)[0].strip()
        if 10 < len(first) < 200:
            semantic.append(first[:180])
    return {
        "episodic_line": episodic,
        "semantic_facts": semantic[:3],
        "kg_entities": [],
    }


async def distill_chat_turn(llm: ILLM, user_message: str, assistant_message: str) -> dict:
    try:
        out = await llm.complete_json(
            SYSTEM,
            f"User message:\n{user_message}\n\nAssistant reply:\n{assistant_message}",
            DISTILL_SCHEMA,
            max_tokens=600,
        )
        if not isinstance(out, dict):
            return _fallback_distill(user_message, assistant_message)
        facts = out.get("semantic_facts") or []
        if not isinstance(facts, list):
            facts = []
        ents = out.get("kg_entities") or []
        if not isinstance(ents, list):
            ents = []
        return {
            "episodic_line": str(out.get("episodic_line") or "").strip(),
            "semantic_facts": [str(x).strip() for x in facts if str(x).strip()][:3],
            "kg_entities": [
                {"title": str(e.get("title", "")).strip(), "detail": str(e.get("detail", "")).strip()}
                for e in ents
                if isinstance(e, dict) and str(e.get("title", "")).strip()
            ][:3],
        }
    except Exception:
        return _fallback_distill(user_message, assistant_message)


def semantic_key(session_id: str, fact: str) -> str:
    h = hashlib.sha256(f"{session_id}:{fact}".encode()).hexdigest()[:16]
    return f"sem-{h}"

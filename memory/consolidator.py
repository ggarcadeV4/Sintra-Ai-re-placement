"""Memory consolidator: extract long-term insights from completed sessions."""
from __future__ import annotations

from datetime import datetime

MIN_MESSAGES_TO_CONSOLIDATE = 8

_SYSTEM = """\
You are a memory consolidation assistant. Analyze the conversation below and extract
insights worth storing as persistent memories for future sessions.

Focus ONLY on:
1. New user preferences or working-style corrections
2. Project decisions or facts made explicit (NOT derivable from code/git)
3. Behavioral feedback given to the AI

Return a JSON object with key "memories" containing a list of objects, each with:
  "name", "type", "description", "content", "confidence"

Return {"memories": []} if nothing new. Keep to AT MOST 3 memories."""


def consolidate_session(messages: list, config: dict) -> list[str]:
    if len(messages) < MIN_MESSAGES_TO_CONSOLIDATE:
        return []
    try:
        from providers import stream, AssistantTurn
        from .store import MemoryEntry, save_memory, check_conflict
        import json

        recent = messages[-40:]
        parts: list[str] = []
        for m in recent:
            role = m.get("role", "")
            content = m.get("content", "")
            if isinstance(content, str) and content.strip():
                prefix = "User" if role == "user" else "Assistant"
                snippet = content[:600].replace("\n", " ")
                parts.append(f"{prefix}: {snippet}")
        if not parts:
            return []
        transcript = "\n".join(parts)
        result_text = ""
        for event in stream(
            model=config.get("model", ""), system=_SYSTEM,
            messages=[{"role": "user", "content": f"Conversation:\n\n{transcript}"}],
            tool_schemas=[], config={**config, "max_tokens": 1024, "no_tools": True},
        ):
            if isinstance(event, AssistantTurn):
                result_text = event.text
                break
        if not result_text:
            return []
        parsed = json.loads(result_text)
        memories_data = parsed.get("memories", [])
        if not isinstance(memories_data, list):
            return []
        saved: list[str] = []
        for m in memories_data[:3]:
            required = ("name", "type", "description", "content")
            if not all(k in m for k in required):
                continue
            entry = MemoryEntry(
                name=str(m["name"]), description=str(m["description"]),
                type=str(m.get("type", "user")), content=str(m["content"]),
                created=datetime.now().strftime("%Y-%m-%d"),
                confidence=float(m.get("confidence", 0.8)), source="consolidator",
            )
            conflict = check_conflict(entry, scope="user")
            if conflict and conflict["existing_confidence"] >= entry.confidence:
                continue
            save_memory(entry, scope="user")
            saved.append(entry.name)
        return saved
    except Exception:
        return []

"""Memory tool registrations: MemorySave, MemoryDelete, MemorySearch, MemoryList.

Importing this module registers the tools into the central registry.
"""
from __future__ import annotations

from datetime import datetime

from tool_registry import ToolDef, register_tool
from .store import MemoryEntry, save_memory, delete_memory, load_index, check_conflict, touch_last_used
from .context import find_relevant_memories
from .scan import scan_all_memories, format_memory_manifest


def _memory_save(params: dict, config: dict) -> str:
    scope = params.get("scope", "user")
    entry = MemoryEntry(
        name=params["name"], description=params["description"],
        type=params["type"], content=params["content"],
        created=datetime.now().strftime("%Y-%m-%d"),
        confidence=float(params.get("confidence", 1.0)),
        source=params.get("source", "user"),
        conflict_group=params.get("conflict_group", ""),
    )
    conflict = check_conflict(entry, scope=scope)
    save_memory(entry, scope=scope)
    scope_label = "project" if scope == "project" else "user"
    msg = f"Memory saved: '{entry.name}' [{entry.type}/{scope_label}]"
    if entry.confidence < 1.0:
        msg += f" (confidence: {entry.confidence:.0%})"
    if conflict:
        msg += f"\n\u26a0 Replaced conflicting memory"
    return msg


def _memory_delete(params: dict, config: dict) -> str:
    name = params["name"]
    scope = params.get("scope", "user")
    delete_memory(name, scope=scope)
    return f"Memory deleted: '{name}' (scope: {scope})"


def _memory_search(params: dict, config: dict) -> str:
    import math, time as _time
    query = params["query"]
    use_ai = params.get("use_ai", False)
    max_results = params.get("max_results", 5)
    results = find_relevant_memories(query, max_results=max_results * 3, use_ai=use_ai, config=config)
    if not results:
        return f"No memories found matching '{query}'."
    now = _time.time()
    for r in results:
        age_days = max(0, (now - r["mtime_s"]) / 86400)
        recency = math.exp(-age_days / 30)
        r["_rank"] = r.get("confidence", 1.0) * recency
    results.sort(key=lambda r: r["_rank"], reverse=True)
    results = results[:max_results]
    for r in results:
        if r.get("file_path"):
            touch_last_used(r["file_path"])
    lines = [f"Found {len(results)} relevant memory/memories for '{query}':"]
    for r in results:
        freshness = f"  \u26a0 {r['freshness_text']}" if r["freshness_text"] else ""
        lines.append(f"[{r['type']}/{r['scope']}] {r['name']}\n  {r['description']}\n  {r['content'][:200]}{freshness}")
    return "\n\n".join(lines)


def _memory_list(params: dict, config: dict) -> str:
    from .store import load_entries
    scope_filter = params.get("scope", "all")
    scopes = ["user", "project"] if scope_filter == "all" else [scope_filter]
    all_entries = []
    for s in scopes:
        all_entries.extend(load_entries(s))
    if not all_entries:
        return "No memories stored."
    lines = [f"{len(all_entries)} memory/memories:"]
    for e in all_entries:
        tag = f"[{e.type:9s}|{e.scope:7s}]"
        lines.append(f"  {tag} {e.name}")
        if e.description:
            lines.append(f"    {e.description}")
    return "\n".join(lines)


register_tool(ToolDef(
    name="MemorySave",
    schema={
        "name": "MemorySave",
        "description": "Save a persistent memory entry as a markdown file with frontmatter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Human-readable name"},
                "type": {"type": "string", "enum": ["user", "feedback", "project", "reference"]},
                "description": {"type": "string", "description": "Short one-line description"},
                "content": {"type": "string", "description": "Body text"},
                "scope": {"type": "string", "enum": ["user", "project"]},
                "confidence": {"type": "number"},
                "source": {"type": "string", "enum": ["user", "model", "tool"]},
                "conflict_group": {"type": "string"},
            },
            "required": ["name", "type", "description", "content"],
        },
    },
    func=_memory_save, read_only=False, concurrent_safe=False,
))

register_tool(ToolDef(
    name="MemoryDelete",
    schema={
        "name": "MemoryDelete",
        "description": "Delete a persistent memory entry by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "scope": {"type": "string", "enum": ["user", "project"]},
            },
            "required": ["name"],
        },
    },
    func=_memory_delete, read_only=False, concurrent_safe=False,
))

register_tool(ToolDef(
    name="MemorySearch",
    schema={
        "name": "MemorySearch",
        "description": "Search persistent memories by keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
                "use_ai": {"type": "boolean"},
                "scope": {"type": "string", "enum": ["user", "project", "all"]},
            },
            "required": ["query"],
        },
    },
    func=_memory_search, read_only=True, concurrent_safe=True,
))

register_tool(ToolDef(
    name="MemoryList",
    schema={
        "name": "MemoryList",
        "description": "List all memory entries with type, scope, and description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["user", "project", "all"]},
            },
        },
    },
    func=_memory_list, read_only=True, concurrent_safe=True,
))

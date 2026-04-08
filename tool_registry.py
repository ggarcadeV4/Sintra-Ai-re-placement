"""Tool plugin registry for nano-claude-code."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

@dataclass
class ToolDef:
    name: str
    schema: Dict[str, Any]
    func: Callable[[Dict[str, Any], Dict[str, Any]], str]
    read_only: bool = False
    concurrent_safe: bool = False

_registry: Dict[str, ToolDef] = {}

def register_tool(tool_def: ToolDef) -> None:
    _registry[tool_def.name] = tool_def

def get_tool(name: str) -> Optional[ToolDef]:
    return _registry.get(name)

def get_all_tools() -> List[ToolDef]:
    return list(_registry.values())

def get_tool_schemas() -> List[Dict[str, Any]]:
    return [t.schema for t in _registry.values()]

def execute_tool(name: str, params: Dict[str, Any], config: Dict[str, Any], max_output: int = 32000) -> str:
    tool = get_tool(name)
    if tool is None:
        return f"Error: tool '{name}' not found."
    try:
        result = tool.func(params, config)
    except Exception as e:
        return f"Error executing {name}: {e}"
    if len(result) > max_output:
        first_half = max_output // 2
        last_quarter = max_output // 4
        truncated = len(result) - first_half - last_quarter
        result = result[:first_half] + f"\n[... {truncated} chars truncated ...]\n" + result[-last_quarter:]
    return result

def clear_registry() -> None:
    _registry.clear()

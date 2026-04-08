"""Multi-agent tool registrations."""
from __future__ import annotations

from tool_registry import ToolDef, register_tool
from .subagent import SubAgentManager, get_agent_definition, load_agent_definitions

_agent_manager: SubAgentManager | None = None

def get_agent_manager() -> SubAgentManager:
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = SubAgentManager()
    return _agent_manager


def _agent_tool(params: dict, config: dict) -> str:
    mgr = get_agent_manager()
    prompt = params["prompt"]
    wait = params.get("wait", True)
    isolation = params.get("isolation", "")
    name = params.get("name", "")
    model_override = params.get("model", "")
    subagent_type = params.get("subagent_type", "")
    system_prompt = config.get("_system_prompt", "You are a helpful assistant.")
    depth = config.get("_depth", 0)
    eff_config = {k: v for k, v in config.items() if not k.startswith("_")}
    if model_override:
        eff_config["model"] = model_override
    agent_def = None
    if subagent_type:
        agent_def = get_agent_definition(subagent_type)
        if agent_def is None:
            return f"Error: unknown subagent_type '{subagent_type}'."
    task = mgr.spawn(prompt, eff_config, system_prompt, depth=depth,
                     agent_def=agent_def, isolation=isolation, name=name)
    if task.status == "failed":
        return f"Error spawning agent: {task.result}"
    if wait:
        mgr.wait(task.id, timeout=300)
        result = task.result or f"(no output — status: {task.status})"
        return f"[Agent: {task.name}]\n\n{result}"
    else:
        return f"Task ID: {task.id}\nName: {task.name}\nStatus: {task.status}"


def _send_message(params: dict, config: dict) -> str:
    mgr = get_agent_manager()
    target = params["to"]
    message = params["message"]
    ok = mgr.send_message(target, message)
    if ok:
        return f"Message queued for agent '{target}'."
    return f"Error: agent '{target}' not found or not running."


def _check_agent_result(params: dict, config: dict) -> str:
    mgr = get_agent_manager()
    task = mgr.tasks.get(params["task_id"])
    if task is None:
        return f"Error: no task with id '{params['task_id']}'"
    lines = [f"Status: {task.status}", f"Name: {task.name}"]
    if task.result:
        lines.append(f"\nResult:\n{task.result}")
    return "\n".join(lines)


def _list_agent_tasks(params: dict, config: dict) -> str:
    mgr = get_agent_manager()
    tasks = mgr.list_tasks()
    if not tasks:
        return "No sub-agent tasks."
    lines = []
    for t in tasks:
        lines.append(f"#{t.id} [{t.status}] {t.name}: {t.prompt[:50]}")
    return "\n".join(lines)


def _list_agent_types(params: dict, config: dict) -> str:
    defs = load_agent_definitions()
    if not defs:
        return "No agent types available."
    lines = ["Available agent types:"]
    for aname, d in sorted(defs.items()):
        lines.append(f"  {aname:20s} [{d.source:8s}] {d.description}")
    return "\n".join(lines)


register_tool(ToolDef(
    name="Agent", schema={"name": "Agent", "description": "Spawn a sub-agent.",
        "input_schema": {"type": "object", "properties": {
            "prompt": {"type": "string"}, "subagent_type": {"type": "string"},
            "name": {"type": "string"}, "model": {"type": "string"},
            "wait": {"type": "boolean"}, "isolation": {"type": "string", "enum": ["worktree"]},
        }, "required": ["prompt"]}},
    func=_agent_tool, read_only=False, concurrent_safe=False,
))

register_tool(ToolDef(
    name="SendMessage", schema={"name": "SendMessage", "description": "Send message to a running agent.",
        "input_schema": {"type": "object", "properties": {
            "to": {"type": "string"}, "message": {"type": "string"},
        }, "required": ["to", "message"]}},
    func=_send_message, read_only=False, concurrent_safe=True,
))

register_tool(ToolDef(
    name="CheckAgentResult", schema={"name": "CheckAgentResult", "description": "Check agent task status.",
        "input_schema": {"type": "object", "properties": {
            "task_id": {"type": "string"},
        }, "required": ["task_id"]}},
    func=_check_agent_result, read_only=True, concurrent_safe=True,
))

register_tool(ToolDef(
    name="ListAgentTasks", schema={"name": "ListAgentTasks", "description": "List all agent tasks.",
        "input_schema": {"type": "object", "properties": {}}},
    func=_list_agent_tasks, read_only=True, concurrent_safe=True,
))

register_tool(ToolDef(
    name="ListAgentTypes", schema={"name": "ListAgentTypes", "description": "List available agent types.",
        "input_schema": {"type": "object", "properties": {}}},
    func=_list_agent_types, read_only=True, concurrent_safe=True,
))

"""Task tools: TaskCreate, TaskUpdate, TaskGet, TaskList."""
from __future__ import annotations

from tool_registry import ToolDef, register_tool
from .store import create_task, get_task, list_tasks, update_task, delete_task
from .types import TaskStatus


def _task_create(params, config):
    task = create_task(params["subject"], params["description"],
                       active_form=params.get("active_form", ""), metadata=params.get("metadata"))
    return f"Task #{task.id} created: {task.subject}"

def _task_update(params, config):
    if params.get("status") == "deleted":
        ok = delete_task(params["task_id"])
        return f"Task #{params['task_id']} deleted." if ok else f"Error: task #{params['task_id']} not found."
    task, updated = update_task(
        params["task_id"], subject=params.get("subject"), description=params.get("description"),
        status=params.get("status"), active_form=params.get("active_form"),
        owner=params.get("owner"), add_blocks=params.get("add_blocks"),
        add_blocked_by=params.get("add_blocked_by"), metadata=params.get("metadata"),
    )
    if task is None:
        return f"Error: task #{params['task_id']} not found."
    if not updated:
        return f"Task #{params['task_id']}: no changes."
    return f"Task #{params['task_id']} updated — changed: {', '.join(updated)}."

def _task_get(params, config):
    task = get_task(params["task_id"])
    if task is None:
        return f"Task #{params['task_id']} not found."
    lines = [f"Task #{task.id}: {task.subject}", f"Status: {task.status.value}",
             f"Description: {task.description}"]
    if task.owner: lines.append(f"Owner: {task.owner}")
    if task.blocked_by: lines.append(f"Blocked by: #{', #'.join(task.blocked_by)}")
    if task.blocks: lines.append(f"Blocks: #{', #'.join(task.blocks)}")
    return "\n".join(lines)

def _task_list(params, config):
    tasks = list_tasks()
    if not tasks:
        return "No tasks."
    resolved = {t.id for t in tasks if t.status == TaskStatus.COMPLETED}
    lines = []
    for task in tasks:
        pending_blockers = [b for b in task.blocked_by if b not in resolved]
        owner_str = f" ({task.owner})" if task.owner else ""
        blocked_str = f" [blocked by #{', #'.join(pending_blockers)}]" if pending_blockers else ""
        lines.append(f"#{task.id} [{task.status.value}] {task.status_icon()} {task.subject}{owner_str}{blocked_str}")
    return "\n".join(lines)


register_tool(ToolDef(name="TaskCreate", schema={"name": "TaskCreate", "description": "Create a new task.",
    "input_schema": {"type": "object", "properties": {
        "subject": {"type": "string"}, "description": {"type": "string"},
        "active_form": {"type": "string"}, "metadata": {"type": "object"},
    }, "required": ["subject", "description"]}},
    func=_task_create, read_only=False, concurrent_safe=True))

register_tool(ToolDef(name="TaskUpdate", schema={"name": "TaskUpdate", "description": "Update a task.",
    "input_schema": {"type": "object", "properties": {
        "task_id": {"type": "string"}, "subject": {"type": "string"},
        "description": {"type": "string"}, "status": {"type": "string",
            "enum": ["pending", "in_progress", "completed", "cancelled", "deleted"]},
        "active_form": {"type": "string"}, "owner": {"type": "string"},
        "add_blocks": {"type": "array", "items": {"type": "string"}},
        "add_blocked_by": {"type": "array", "items": {"type": "string"}},
        "metadata": {"type": "object"},
    }, "required": ["task_id"]}},
    func=_task_update, read_only=False, concurrent_safe=True))

register_tool(ToolDef(name="TaskGet", schema={"name": "TaskGet", "description": "Get a task by ID.",
    "input_schema": {"type": "object", "properties": {
        "task_id": {"type": "string"},
    }, "required": ["task_id"]}},
    func=_task_get, read_only=True, concurrent_safe=True))

register_tool(ToolDef(name="TaskList", schema={"name": "TaskList", "description": "List all tasks.",
    "input_schema": {"type": "object", "properties": {}}},
    func=_task_list, read_only=True, concurrent_safe=True))

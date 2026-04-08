"""Skill tool: lets the model invoke skills by name."""
from __future__ import annotations
from tool_registry import ToolDef, register_tool
from .loader import find_skill, load_skills, substitute_arguments

def _skill_tool(params, config):
    skill_name = params.get("name", "").strip()
    args = params.get("args", "")
    skill = None
    for s in load_skills():
        if s.name == skill_name:
            skill = s
            break
    if skill is None:
        skill = find_skill(skill_name)
    if skill is None:
        names = [s.name for s in load_skills()]
        return f"Error: skill '{skill_name}' not found. Available: {', '.join(names)}"
    rendered = substitute_arguments(skill.prompt, args, skill.arguments)
    message = f"[Skill: {skill.name}]\n\n{rendered}"
    import agent as _agent
    system_prompt = config.get("_system_prompt", "")
    output_parts = []
    sub_state = _agent.AgentState()
    sub_config = {**config, "_depth": config.get("_depth", 0) + 1}
    try:
        for event in _agent.run(message, sub_state, sub_config, system_prompt):
            if hasattr(event, "text"):
                output_parts.append(event.text)
    except Exception as e:
        return f"Skill execution error: {e}"
    return "".join(output_parts) or "(skill completed with no text output)"

def _skill_list_tool(params, config):
    skills = load_skills()
    if not skills:
        return "No skills available."
    lines = ["Available skills:\n"]
    for s in skills:
        triggers = ", ".join(s.triggers)
        hint = f"  args: {s.argument_hint}" if s.argument_hint else ""
        when = f"\n    when: {s.when_to_use}" if s.when_to_use else ""
        lines.append(f"- **{s.name}** [{triggers}]{hint}\n  {s.description}{when}")
    return "\n".join(lines)

def _register():
    register_tool(ToolDef(
        name="Skill",
        schema={"name": "Skill", "description": "Invoke a named skill.",
            "input_schema": {"type": "object", "properties": {
                "name": {"type": "string"}, "args": {"type": "string", "default": ""},
            }, "required": ["name"]}},
        func=_skill_tool, read_only=False, concurrent_safe=False,
    ))
    register_tool(ToolDef(
        name="SkillList",
        schema={"name": "SkillList", "description": "List available skills.",
            "input_schema": {"type": "object", "properties": {}}},
        func=_skill_list_tool, read_only=True, concurrent_safe=True,
    ))

_register()

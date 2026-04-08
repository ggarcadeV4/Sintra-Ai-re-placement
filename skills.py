"""Backward-compatibility shim — real implementation is in skill/ package."""
from skill.loader import (  # noqa: F401
    SkillDef,
    load_skills,
    find_skill,
    substitute_arguments,
    _parse_skill_file,
    _parse_list_field,
)
from skill.executor import execute_skill  # noqa: F401
from skill.loader import _get_skill_paths as _gsp
SKILL_PATHS = _gsp()

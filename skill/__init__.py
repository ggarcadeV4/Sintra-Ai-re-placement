"""skill package — reusable prompt templates (skills)."""
from .loader import (
    SkillDef, load_skills, find_skill,
    substitute_arguments, register_builtin_skill,
    _parse_skill_file, _parse_list_field,
)
from .executor import execute_skill
from . import builtin as _builtin

"""Memory type taxonomy and system-prompt guidance text."""

MEMORY_TYPES = ["user", "feedback", "project", "reference"]

MEMORY_TYPE_DESCRIPTIONS: dict[str, str] = {
    "user": "Information about the user's role, goals, responsibilities, and knowledge.",
    "feedback": "Guidance the user has given about how to approach work.",
    "project": "Ongoing work, goals, bugs, or incidents not derivable from code or git history.",
    "reference": "Pointers to external systems (issue trackers, dashboards, Slack channels, docs).",
}

WHAT_NOT_TO_SAVE = """\
## What NOT to save in memory
- Code patterns, conventions, architecture, file paths, or project structure.
- Git history, recent changes, who-changed-what.
- Debugging solutions or fix recipes.
- Anything already documented in CLAUDE.md files.
- Ephemeral task details."""

MEMORY_FORMAT_EXAMPLE = """\
```markdown
---
name: {{memory name}}
description: {{one-line description}}
type: {{user | feedback | project | reference}}
---

{{memory content}}
```"""

MEMORY_SYSTEM_PROMPT = """\
## Memory system

You have a persistent, file-based memory system. Memories are stored as markdown files with
YAML frontmatter. Build this up over time so future conversations have context.

**Types** (save only what cannot be derived from the codebase):
- **user** — role, goals, knowledge, preferences
- **feedback** — guidance on how to work
- **project** — ongoing work, decisions, deadlines not in git history
- **reference** — pointers to external systems

**Format**:
{format_example}

**What NOT to save**: code patterns, architecture, git history, debugging fixes,
anything already in CLAUDE.md, or ephemeral task state.
""".format(format_example=MEMORY_FORMAT_EXAMPLE)

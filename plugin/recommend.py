"""Plugin recommendation engine."""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from .types import PluginManifest, PluginScope
from .store import list_plugins, USER_PLUGIN_DIR

BUILTIN_MARKETPLACE = [
    {"name": "git-tools", "description": "Extra git helpers",
     "tags": ["git", "vcs", "diff", "blame"],
     "source": "https://github.com/nano-claude-plugins/git-tools"},
    {"name": "python-linter", "description": "Run ruff/mypy/black",
     "tags": ["python", "lint", "format", "mypy", "ruff", "black"],
     "source": "https://github.com/nano-claude-plugins/python-linter"},
    {"name": "docker-tools", "description": "Docker container management",
     "tags": ["docker", "container", "compose", "kubernetes"],
     "source": "https://github.com/nano-claude-plugins/docker-tools"},
    {"name": "web-scraper", "description": "Advanced web scraping with JS rendering",
     "tags": ["web", "scrape", "html", "browser", "playwright"],
     "source": "https://github.com/nano-claude-plugins/web-scraper"},
    {"name": "sql-tools", "description": "Query and inspect SQL databases",
     "tags": ["sql", "database", "db", "sqlite", "postgres", "mysql"],
     "source": "https://github.com/nano-claude-plugins/sql-tools"},
    {"name": "test-runner", "description": "Run pytest/unittest",
     "tags": ["test", "pytest", "unittest", "coverage"],
     "source": "https://github.com/nano-claude-plugins/test-runner"},
    {"name": "diagram-tools", "description": "Generate Mermaid/PlantUML diagrams",
     "tags": ["diagram", "mermaid", "plantuml", "uml", "flowchart"],
     "source": "https://github.com/nano-claude-plugins/diagram-tools"},
    {"name": "aws-tools", "description": "AWS CLI wrapper tools",
     "tags": ["aws", "cloud", "s3", "ec2", "lambda"],
     "source": "https://github.com/nano-claude-plugins/aws-tools"},
]

@dataclass
class PluginRecommendation:
    name: str
    description: str
    source: str
    score: float
    reasons: list[str]
    installed: bool = False
    enabled: bool = False

def _tokenize(text):
    return set(re.findall(r"\b[a-z0-9_\-]+\b", text.lower()))

def _score_against_context(entry, context_tokens):
    score = 0.0
    reasons = []
    name_tokens = _tokenize(entry.get("name", ""))
    desc_tokens = _tokenize(entry.get("description", ""))
    tag_tokens = set()
    for tag in entry.get("tags", []):
        tag_tokens.update(_tokenize(tag))
    tag_hits = tag_tokens & context_tokens
    if tag_hits:
        score += len(tag_hits) * 3.0
        reasons.append(f"tags match: {', '.join(sorted(tag_hits))}")
    name_hits = name_tokens & context_tokens
    if name_hits:
        score += len(name_hits) * 2.0
        reasons.append(f"name match: {', '.join(sorted(name_hits))}")
    desc_hits = desc_tokens & context_tokens - {"the", "a", "an", "and", "or", "of", "to", "in", "for", "with"}
    if desc_hits:
        score += len(desc_hits) * 0.5
    return score, reasons

def recommend_plugins(context, top_n=5, include_installed=False):
    context_tokens = _tokenize(context)
    if not context_tokens:
        return []
    installed_entries = list_plugins()
    installed_names = {e.name for e in installed_entries}
    installed_enabled = {e.name for e in installed_entries if e.enabled}
    for entry in installed_entries:
        if entry.manifest:
            for tag in entry.manifest.tags:
                context_tokens.update(_tokenize(tag))
    results = []
    for mp_entry in BUILTIN_MARKETPLACE:
        name = mp_entry["name"]
        is_installed = name in installed_names
        is_enabled = name in installed_enabled
        if is_installed and not include_installed:
            continue
        score, reasons = _score_against_context(mp_entry, context_tokens)
        if score > 0:
            results.append(PluginRecommendation(
                name=name, description=mp_entry.get("description", ""),
                source=mp_entry.get("source", ""), score=score,
                reasons=reasons, installed=is_installed, enabled=is_enabled,
            ))
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_n]

def recommend_from_files(paths, top_n=5):
    context_parts = []
    ext_map = {
        ".py": "python", ".ts": "typescript javascript", ".tsx": "typescript react javascript",
        ".js": "javascript", ".rs": "rust", ".go": "golang", ".java": "java",
        ".sql": "sql database", ".dockerfile": "docker container",
        ".yaml": "yaml config", ".yml": "yaml config docker",
        ".tf": "terraform aws cloud", ".md": "markdown docs",
    }
    for p in paths:
        label = ext_map.get(p.suffix.lower(), "")
        if label:
            context_parts.append(label)
    return recommend_plugins(" ".join(context_parts), top_n=top_n)

def format_recommendations(recs):
    if not recs:
        return "No plugin recommendations for the current context."
    lines = ["Plugin recommendations:"]
    for i, rec in enumerate(recs, 1):
        status = " [installed]" if rec.installed else ""
        lines.append(f"  {i}. {rec.name}{status} \u2014 {rec.description}")
        if rec.reasons:
            lines.append(f"     Reason: {'; '.join(rec.reasons)}")
        lines.append(f"     Install: /plugin install {rec.name}@{rec.source}")
    return "\n".join(lines)

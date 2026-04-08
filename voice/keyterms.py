"""Voice keyterms: domain-specific vocabulary hints for STT accuracy."""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

GLOBAL_KEYTERMS = [
    "MCP", "grep", "regex", "regex pattern", "ripgrep", "localhost",
    "codebase", "webhook", "OAuth", "gRPC", "JSON", "YAML", "dotfiles",
    "symlink", "subprocess", "subagent", "worktree",
    "TypeScript", "JavaScript", "Python", "Rust", "Golang",
    "Dockerfile", "bash", "pytest", "linter", "formatter",
    "middleware", "endpoint", "namespace", "async", "await",
    "refactor", "deprecate", "serialize", "deserialize",
    "Pydantic", "FastAPI", "SQLAlchemy",
]
MAX_KEYTERMS = 50

def split_identifier(name):
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    parts = re.split(r"[-_./\s]+", spaced)
    return [p.strip() for p in parts if 3 <= len(p.strip()) <= 20]

def _git_branch():
    try:
        result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=3)
        branch = result.stdout.strip()
        return branch if branch and branch != "HEAD" else None
    except Exception:
        return None

def _project_root():
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, timeout=3)
        root = result.stdout.strip()
        if root:
            return Path(root)
    except Exception:
        pass
    return Path.cwd()

def _recent_py_files(root, limit=20):
    try:
        result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                                capture_output=True, text=True, timeout=5, cwd=str(root))
        files = [root / f for f in result.stdout.splitlines()
                 if f.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"))]
        files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        return files[:limit]
    except Exception:
        return []

def get_voice_keyterms(recent_files=None):
    terms = list(GLOBAL_KEYTERMS)
    root = _project_root()
    if root and root.name:
        name = root.name
        if 2 < len(name) <= 50:
            terms.append(name)
        terms.extend(split_identifier(name))
    branch = _git_branch()
    if branch:
        terms.extend(split_identifier(branch))
    files = [Path(f) for f in (recent_files or [])] + _recent_py_files(root or Path.cwd())
    for fpath in files:
        if len(terms) >= MAX_KEYTERMS:
            break
        stem = fpath.stem
        if stem:
            terms.extend(split_identifier(stem))
    seen = set()
    result = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            result.append(t)
        if len(result) >= MAX_KEYTERMS:
            break
    return result

"""Plugin system types: manifest, entry, scope."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

class PluginScope(str, Enum):
    USER    = "user"
    PROJECT = "project"

@dataclass
class PluginManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    homepage: str = ""

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data.get("name", "unknown"), version=str(data.get("version", "0.1.0")),
            description=data.get("description", ""), author=data.get("author", ""),
            tags=data.get("tags", []), tools=data.get("tools", []),
            skills=data.get("skills", []), mcp_servers=data.get("mcp_servers", {}),
            dependencies=data.get("dependencies", []), homepage=data.get("homepage", ""),
        )

    @classmethod
    def from_plugin_dir(cls, plugin_dir):
        json_file = plugin_dir / "plugin.json"
        if json_file.exists():
            import json
            try:
                return cls.from_dict(json.loads(json_file.read_text()))
            except Exception:
                pass
        md_file = plugin_dir / "PLUGIN.md"
        if md_file.exists():
            return cls._from_md(md_file)
        return None

    @classmethod
    def _from_md(cls, md_file):
        text = md_file.read_text()
        if not text.startswith("---"):
            return None
        end = text.find("---", 3)
        if end == -1:
            return None
        frontmatter = text[3:end].strip()
        try:
            import yaml
            data = yaml.safe_load(frontmatter)
        except ImportError:
            data = {}
            for line in frontmatter.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    data[k.strip()] = v.strip()
        if isinstance(data, dict):
            return cls.from_dict(data)
        return None

@dataclass
class PluginEntry:
    name: str
    scope: PluginScope
    source: str
    install_dir: Path
    enabled: bool = True
    manifest: PluginManifest | None = None

    @property
    def qualified_name(self):
        return f"{self.name}@{self.scope.value}"

    def to_dict(self):
        return {
            "name": self.name, "scope": self.scope.value,
            "source": self.source, "install_dir": str(self.install_dir),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data["name"], scope=PluginScope(data.get("scope", "user")),
            source=data.get("source", ""), install_dir=Path(data["install_dir"]),
            enabled=data.get("enabled", True),
        )

def parse_plugin_identifier(identifier):
    if "@" in identifier:
        name, _, source = identifier.partition("@")
        return name.strip(), source.strip()
    return identifier.strip(), None

def sanitize_plugin_name(name):
    return re.sub(r"[^\w]", "_", name)

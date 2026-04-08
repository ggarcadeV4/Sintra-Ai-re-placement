"""Load MCP server configs from .mcp.json files."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List
from .types import MCPServerConfig

USER_MCP_CONFIG = Path.home() / ".nano_claude" / "mcp.json"
PROJECT_MCP_NAME = ".mcp.json"

def _load_file(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("mcpServers", {})
    except Exception:
        return {}

def load_mcp_configs():
    servers = _load_file(USER_MCP_CONFIG)
    p = Path.cwd()
    for _ in range(10):
        candidate = p / PROJECT_MCP_NAME
        if candidate.exists():
            servers.update(_load_file(candidate))
            break
        parent = p.parent
        if parent == p:
            break
        p = parent
    return {name: MCPServerConfig.from_dict(name, raw) for name, raw in servers.items()}

def save_user_mcp_config(servers):
    USER_MCP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if USER_MCP_CONFIG.exists():
        try:
            existing = json.loads(USER_MCP_CONFIG.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing["mcpServers"] = servers
    USER_MCP_CONFIG.write_text(json.dumps(existing, indent=2), encoding="utf-8")

def add_server_to_user_config(name, raw):
    existing = {}
    if USER_MCP_CONFIG.exists():
        try:
            existing = json.loads(USER_MCP_CONFIG.read_text(encoding="utf-8"))
        except Exception:
            pass
    mcp_servers = existing.get("mcpServers", {})
    mcp_servers[name] = raw
    existing["mcpServers"] = mcp_servers
    USER_MCP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    USER_MCP_CONFIG.write_text(json.dumps(existing, indent=2), encoding="utf-8")

def remove_server_from_user_config(name):
    if not USER_MCP_CONFIG.exists():
        return False
    try:
        existing = json.loads(USER_MCP_CONFIG.read_text(encoding="utf-8"))
        mcp_servers = existing.get("mcpServers", {})
        if name not in mcp_servers:
            return False
        del mcp_servers[name]
        existing["mcpServers"] = mcp_servers
        USER_MCP_CONFIG.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False

def list_config_files():
    found = []
    if USER_MCP_CONFIG.exists():
        found.append(USER_MCP_CONFIG)
    p = Path.cwd()
    for _ in range(10):
        candidate = p / PROJECT_MCP_NAME
        if candidate.exists():
            found.append(candidate)
            break
        parent = p.parent
        if parent == p:
            break
        p = parent
    return found

"""MCP type definitions: server configs, tool descriptors, connection state."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

class MCPTransport(str, Enum):
    STDIO = "stdio"
    SSE   = "sse"
    HTTP  = "http"
    WS    = "ws"

@dataclass
class MCPServerConfig:
    name: str
    transport: MCPTransport = MCPTransport.STDIO
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    disabled: bool = False

    @classmethod
    def from_dict(cls, name, d):
        transport_str = d.get("type", "stdio").lower()
        try:
            transport = MCPTransport(transport_str)
        except ValueError:
            transport = MCPTransport.STDIO
        return cls(
            name=name, transport=transport, command=d.get("command", ""),
            args=d.get("args", []), env=d.get("env", {}),
            url=d.get("url", ""), headers=d.get("headers", {}),
            timeout=int(d.get("timeout", 30)), disabled=bool(d.get("disabled", False)),
        )

class MCPServerState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING   = "connecting"
    CONNECTED    = "connected"
    ERROR        = "error"

@dataclass
class MCPTool:
    server_name: str
    tool_name: str
    qualified_name: str
    description: str
    input_schema: Dict[str, Any]
    read_only: bool = False

    def to_tool_schema(self):
        return {
            "name": self.qualified_name,
            "description": f"[MCP:{self.server_name}] {self.description}",
            "input_schema": self.input_schema or {"type": "object", "properties": {}},
        }

def make_request(method, params, req_id):
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg

def make_notification(method, params=None):
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg

MCP_PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "nano-claude-code", "version": "1.0.0"}
INIT_PARAMS = {
    "protocolVersion": MCP_PROTOCOL_VERSION,
    "capabilities": {"tools": {}, "roots": {"listChanged": False}},
    "clientInfo": CLIENT_INFO,
}

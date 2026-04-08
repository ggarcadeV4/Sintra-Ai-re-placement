"""Register MCP tools into the central tool_registry."""
from __future__ import annotations
import threading
from typing import Dict, Optional
from tool_registry import ToolDef, register_tool
from .client import MCPClient, MCPManager, get_mcp_manager
from .config import load_mcp_configs
from .types import MCPServerConfig, MCPTool

_initialized = False
_init_lock = threading.Lock()
_connect_errors: Dict[str, Optional[str]] = {}

def _make_mcp_func(qualified_name):
    def _mcp_tool(params, config):
        mgr = get_mcp_manager()
        try:
            return mgr.call_tool(qualified_name, params)
        except Exception as e:
            return f"Error calling MCP tool '{qualified_name}': {e}"
    return _mcp_tool

def _register_tool(tool):
    td = ToolDef(
        name=tool.qualified_name, schema=tool.to_tool_schema(),
        func=_make_mcp_func(tool.qualified_name),
        read_only=tool.read_only, concurrent_safe=False,
    )
    register_tool(td)

def initialize_mcp(verbose=False):
    global _initialized, _connect_errors
    with _init_lock:
        if _initialized:
            return _connect_errors
        configs = load_mcp_configs()
        if not configs:
            _initialized = True
            return {}
        mgr = get_mcp_manager()
        for cfg in configs.values():
            mgr.add_server(cfg)
        errors = mgr.connect_all()
        _connect_errors = errors
        for client in mgr.list_servers():
            if client.state.value == "connected":
                for tool in client._tools:
                    _register_tool(tool)
        _initialized = True
        return errors

def reload_mcp():
    global _initialized
    with _init_lock:
        _initialized = False
    return initialize_mcp()

def refresh_server(server_name):
    mgr = get_mcp_manager()
    client = next((c for c in mgr.list_servers() if c.config.name == server_name), None)
    if client is None:
        return f"Server '{server_name}' not configured"
    try:
        mgr.reload_server(server_name)
        for tool in client._tools:
            _register_tool(tool)
        return None
    except Exception as e:
        return str(e)

def get_connect_errors():
    return dict(_connect_errors)

def _background_init():
    try:
        initialize_mcp()
    except Exception:
        pass

_bg_thread = threading.Thread(target=_background_init, daemon=True)
_bg_thread.start()

"""Configuration management for nano claude (multi-provider)."""
import os
import json
from pathlib import Path

CONFIG_DIR        = Path.home() / ".nano_claude"
CONFIG_FILE       = CONFIG_DIR  / "config.json"
HISTORY_FILE      = CONFIG_DIR  / "input_history.txt"
SESSIONS_DIR      = CONFIG_DIR  / "sessions"
DAILY_DIR         = SESSIONS_DIR / "daily"
SESSION_HIST_FILE = SESSIONS_DIR / "history.json"
MR_SESSION_DIR    = SESSIONS_DIR / "mr_sessions"

DEFAULTS = {
    "model":            "ollama/gemma4",
    "max_tokens":       40000,
    "permission_mode":  "auto",
    "verbose":          False,
    "thinking":         False,
    "thinking_budget":  10000,
    "custom_base_url":  "",
    "max_tool_output":  32000,
    "max_agent_depth":  3,
    "max_concurrent_agents": 3,
    "session_daily_limit":   10,
    "session_history_limit": 200,
}

def load_config() -> dict:
    CONFIG_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except Exception:
            pass
    if cfg.get("api_key") and not cfg.get("anthropic_api_key"):
        cfg["anthropic_api_key"] = cfg.pop("api_key")
    if not cfg.get("anthropic_api_key"):
        cfg["anthropic_api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
    return cfg

def save_config(cfg: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    data = {k: v for k, v in cfg.items() if not k.startswith("_")}
    CONFIG_FILE.write_text(json.dumps(data, indent=2))

def current_provider(cfg: dict) -> str:
    from providers import detect_provider
    return detect_provider(cfg.get("model", "claude-opus-4-6"))

def has_api_key(cfg: dict) -> bool:
    from providers import get_api_key
    pname = current_provider(cfg)
    key = get_api_key(pname, cfg)
    return bool(key)

def calc_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    from providers import calc_cost as _cc
    return _cc(model, in_tokens, out_tokens)

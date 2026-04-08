"""Plugin store: install/uninstall/enable/disable/update."""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from pathlib import Path
from .types import PluginEntry, PluginManifest, PluginScope, parse_plugin_identifier, sanitize_plugin_name

USER_PLUGIN_DIR = Path.home() / ".nano_claude" / "plugins"
USER_PLUGIN_CFG = Path.home() / ".nano_claude" / "plugins.json"

def _project_plugin_dir():
    return Path.cwd() / ".nano_claude" / "plugins"

def _project_plugin_cfg():
    return Path.cwd() / ".nano_claude" / "plugins.json"

def _read_cfg(cfg_path):
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text())
        except Exception:
            pass
    return {"plugins": {}}

def _write_cfg(cfg_path, data):
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(data, indent=2))

def _plugin_dir_for(scope):
    return USER_PLUGIN_DIR if scope == PluginScope.USER else _project_plugin_dir()

def _plugin_cfg_for(scope):
    return USER_PLUGIN_CFG if scope == PluginScope.USER else _project_plugin_cfg()

def list_plugins(scope=None):
    entries = []
    scopes = [PluginScope.USER, PluginScope.PROJECT] if scope is None else [scope]
    for sc in scopes:
        cfg = _read_cfg(_plugin_cfg_for(sc))
        for name, data in cfg.get("plugins", {}).items():
            entry = PluginEntry.from_dict(data)
            entry.manifest = PluginManifest.from_plugin_dir(entry.install_dir)
            entries.append(entry)
    return entries

def get_plugin(name, scope=None):
    for entry in list_plugins(scope):
        if entry.name == name:
            return entry
    return None

def _is_git_url(source):
    return (source.startswith("https://") or source.startswith("git@")
            or source.startswith("http://") or source.endswith(".git"))

def _clone_plugin(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["git", "clone", "--depth", "1", url, str(dest)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return False, f"git clone failed: {result.stderr.strip()}"
    return True, "cloned"

def _install_dependencies(deps):
    result = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet"] + deps,
                            capture_output=True, text=True)
    if result.returncode != 0:
        return False, f"pip install failed: {result.stderr.strip()}"
    return True, "deps installed"

def _save_entry(entry):
    cfg_path = _plugin_cfg_for(entry.scope)
    data = _read_cfg(cfg_path)
    data.setdefault("plugins", {})[entry.name] = entry.to_dict()
    _write_cfg(cfg_path, data)

def _remove_entry(name, scope):
    cfg_path = _plugin_cfg_for(scope)
    data = _read_cfg(cfg_path)
    data.get("plugins", {}).pop(name, None)
    _write_cfg(cfg_path, data)

def install_plugin(identifier, scope=PluginScope.USER, force=False):
    name, source = parse_plugin_identifier(identifier)
    safe_name = sanitize_plugin_name(name)
    existing = get_plugin(safe_name, scope)
    if existing and not force:
        return False, f"Plugin '{safe_name}' already installed. Use --force to reinstall."
    plugin_dir = _plugin_dir_for(scope) / safe_name
    try:
        if source is None:
            local = Path(name)
            if local.exists() and local.is_dir():
                source = str(local.resolve())
            else:
                return False, f"No source specified for '{name}'."
        if plugin_dir.exists() and force:
            shutil.rmtree(plugin_dir)
        if _is_git_url(source):
            ok, msg = _clone_plugin(source, plugin_dir)
            if not ok:
                return False, msg
        else:
            local_src = Path(source)
            if not local_src.exists():
                return False, f"Local path not found: {source}"
            shutil.copytree(str(local_src), str(plugin_dir))
        manifest = PluginManifest.from_plugin_dir(plugin_dir)
        if manifest is None:
            manifest = PluginManifest(name=safe_name, description="(no manifest)")
        if manifest.dependencies:
            dep_ok, dep_msg = _install_dependencies(manifest.dependencies)
            if not dep_ok:
                return False, dep_msg
        entry = PluginEntry(name=safe_name, scope=scope, source=source,
                            install_dir=plugin_dir, enabled=True, manifest=manifest)
        _save_entry(entry)
        return True, f"Plugin '{safe_name}' installed successfully."
    except Exception as e:
        return False, f"Install failed: {e}"

def uninstall_plugin(name, scope=None, keep_data=False):
    entry = get_plugin(name, scope)
    if entry is None:
        return False, f"Plugin '{name}' not found."
    if not keep_data and entry.install_dir.exists():
        shutil.rmtree(entry.install_dir)
    _remove_entry(entry.name, entry.scope)
    return True, f"Plugin '{name}' uninstalled."

def _set_enabled(name, scope, enabled):
    entry = get_plugin(name, scope)
    if entry is None:
        return False, f"Plugin '{name}' not found."
    entry.enabled = enabled
    _save_entry(entry)
    state = "enabled" if enabled else "disabled"
    return True, f"Plugin '{name}' {state}."

def enable_plugin(name, scope=None):
    return _set_enabled(name, scope, True)

def disable_plugin(name, scope=None):
    return _set_enabled(name, scope, False)

def disable_all_plugins(scope=None):
    entries = list_plugins(scope)
    if not entries:
        return True, "No plugins to disable."
    for entry in entries:
        entry.enabled = False
        _save_entry(entry)
    return True, f"Disabled {len(entries)} plugin(s)."

def update_plugin(name, scope=None):
    entry = get_plugin(name, scope)
    if entry is None:
        return False, f"Plugin '{name}' not found."
    if not _is_git_url(entry.source):
        return False, f"Plugin '{name}' was installed locally; cannot auto-update."
    if not entry.install_dir.exists():
        return False, f"Install directory missing: {entry.install_dir}"
    result = subprocess.run(["git", "pull", "--ff-only"],
                            cwd=str(entry.install_dir), capture_output=True, text=True)
    if result.returncode != 0:
        return False, f"git pull failed: {result.stderr.strip()}"
    manifest = PluginManifest.from_plugin_dir(entry.install_dir)
    if manifest and manifest.dependencies:
        _install_dependencies(manifest.dependencies)
    return True, f"Plugin '{name}' updated. {result.stdout.strip()}"

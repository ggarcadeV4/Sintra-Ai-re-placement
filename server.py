"""Arcade OS — FastAPI server wrapping the existing agent loop.

Serves the GUI and exposes WebSocket + REST endpoints.
Each WebSocket connection gets its own AgentState (thread-safe by design).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import db
from config import load_config

DEFAULT_SYSTEM_PROMPT = """You are Arcade OS, a helpful AI assistant running locally on the user's machine.
You are part of a personal business operating system. Be concise, friendly, and action-oriented.
When the user asks you to do something, do it. When they ask a question, answer it directly.
You have access to tools for reading/writing files, running commands, and searching the web."""

_agent_loaded = False
_agent_error = None

def _ensure_agent():
    global _agent_loaded, _agent_error
    if _agent_loaded:
        return _agent_error is None
    try:
        global agent_run, TextChunk, ThinkingChunk, ToolStart, ToolEnd, TurnDone, PermissionRequest, AgentState
        from agent import (
            AgentState, run as agent_run,
            TextChunk, ThinkingChunk, ToolStart, ToolEnd, TurnDone, PermissionRequest,
        )
        _agent_loaded = True
        print("[Arcade OS] Agent module loaded successfully")
        return True
    except Exception as e:
        _agent_loaded = True
        _agent_error = str(e)
        print(f"[Arcade OS] WARNING: Agent failed to load: {e}")
        traceback.print_exc()
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.get_db()
    print(f"[Arcade OS] Database ready at {db.DB_PATH}")
    _ensure_agent()
    print("[Arcade OS] Server running \u2014 open http://127.0.0.1:8765")
    yield
    await db.close_db()
    print("[Arcade OS] Shutting down.")

app = FastAPI(title="Arcade OS", lifespan=lifespan)

STITCH_DIR = PROJECT_ROOT / "stitch_exports"
app.mount("/stitch_exports", StaticFiles(directory=str(STITCH_DIR)), name="stitch")

@app.get("/")
async def index():
    return FileResponse(str(STITCH_DIR / "session1_unified_shell.html"))

@app.get("/api/health")
async def health():
    cfg = load_config()
    configured_model = cfg.get("model", "ollama/gemma4")
    ollama_ok = False
    ollama_models = []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                ollama_ok = True
                data = resp.json()
                ollama_models = [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    resolved_model = await _resolve_model(configured_model) if ollama_ok else configured_model
    return {
        "status": "ok", "model": resolved_model, "configured_model": configured_model,
        "ollama_connected": ollama_ok, "ollama_models": ollama_models,
        "agent_loaded": _agent_error is None if _agent_loaded else "pending",
        "agent_error": _agent_error,
    }

@app.get("/api/models")
async def list_models():
    models = await _get_ollama_models()
    cfg = load_config()
    extras = []
    if cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY"):
        extras.append({"id": "gemini/gemini-2.5-flash", "name": "Gemini 2.5 Flash", "provider": "gemini"})
        extras.append({"id": "gemini/gemini-2.5-pro", "name": "Gemini 2.5 Pro", "provider": "gemini"})
    ollama_list = [{"id": f"ollama/{m}", "name": m, "provider": "ollama"} for m in models]
    return {"models": ollama_list + extras}

@app.get("/api/conversations")
async def list_conversations():
    return await db.list_conversations()

@app.post("/api/conversations")
async def create_conversation():
    return await db.create_conversation()

@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    conv = await db.get_conversation(conv_id)
    if not conv:
        return JSONResponse({"error": "Not found"}, status_code=404)
    messages = await db.get_messages(conv_id)
    return {"conversation": conv, "messages": messages}

@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    deleted = await db.delete_conversation(conv_id)
    if not deleted:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {"deleted": True}

_MODEL_PREFERENCES = ["gemma4", "gemma3", "phi4-mini", "llama3.2", "qwen2.5-coder", "mistral"]

async def _get_ollama_models() -> list[str]:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []

async def _resolve_model(configured_model: str) -> str:
    if not configured_model.startswith("ollama/"):
        return configured_model
    short_name = configured_model.replace("ollama/", "")
    available = await _get_ollama_models()
    if not available:
        return configured_model
    for m in available:
        if m == short_name or m.startswith(short_name.split(":")[0]):
            resolved = f"ollama/{m}"
            if resolved != configured_model:
                print(f"[Model] Resolved {configured_model} -> {resolved}")
            return resolved
    for pref in _MODEL_PREFERENCES:
        for m in available:
            if m.startswith(pref):
                print(f"[Model] {short_name} not found, falling back to: ollama/{m}")
                return f"ollama/{m}"
    if available:
        fallback = f"ollama/{available[0]}"
        print(f"[Model] Using first available model: {fallback}")
        return fallback
    return configured_model

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    print("[WS] Client connected")
    if not _ensure_agent():
        await websocket.send_json({"type": "error", "data": f"Agent module failed to load: {_agent_error}"})
        await websocket.close()
        return
    agent_state = AgentState()
    cfg = load_config()
    if "model" not in cfg:
        cfg["model"] = "ollama/gemma4"
    cfg["model"] = await _resolve_model(cfg["model"])
    cfg["permission_mode"] = "accept-all"
    print(f"[WS] Using model: {cfg['model']}")
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "data": "Invalid JSON"})
                continue
            user_message = payload.get("message", "").strip()
            conv_id = payload.get("conversation_id")
            model_override = payload.get("model")
            if not user_message:
                await websocket.send_json({"type": "error", "data": "Empty message"})
                continue
            if model_override and model_override != cfg["model"]:
                cfg["model"] = model_override
                print(f"[WS] Model switched to: {cfg['model']}")
                agent_state = AgentState()
            print(f"[WS] User message ({cfg['model']}): {user_message[:80]}...")
            if conv_id:
                await db.add_message(conv_id, "user", user_message)
                conv = await db.get_conversation(conv_id)
                if conv and conv["title"] == "New Chat":
                    title = user_message[:60] + ("..." if len(user_message) > 60 else "")
                    await db.update_conversation_title(conv_id, title)
            loop = asyncio.get_running_loop()
            event_queue: asyncio.Queue = asyncio.Queue()
            def _threaded_agent():
                try:
                    print(f"[Agent] Starting generation with model {cfg['model']}...")
                    event_count = 0
                    for event in agent_run(
                        user_message=user_message, state=agent_state,
                        config=cfg, system_prompt=DEFAULT_SYSTEM_PROMPT,
                    ):
                        event_count += 1
                        asyncio.run_coroutine_threadsafe(event_queue.put(event), loop).result(timeout=10)
                    print(f"[Agent] Generation complete -- {event_count} events")
                except Exception as e:
                    tb = traceback.format_exc()
                    print(f"[Agent] ERROR in generation:\n{tb}")
                    asyncio.run_coroutine_threadsafe(
                        event_queue.put(("ERROR", f"{type(e).__name__}: {e}")), loop
                    ).result(timeout=10)
                finally:
                    asyncio.run_coroutine_threadsafe(event_queue.put(None), loop).result(timeout=10)
            loop.run_in_executor(None, _threaded_agent)
            full_text = ""
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(event_queue.get(), timeout=120)
                    except asyncio.TimeoutError:
                        print("[WS] Agent timeout")
                        await websocket.send_json({"type": "error", "data": "Response timed out."})
                        break
                    if event is None:
                        break
                    if isinstance(event, tuple) and len(event) == 2 and event[0] == "ERROR":
                        await websocket.send_json({"type": "error", "data": event[1]})
                        break
                    if isinstance(event, TextChunk):
                        full_text += event.text
                        await websocket.send_json({"type": "text_chunk", "data": event.text})
                    elif isinstance(event, ThinkingChunk):
                        await websocket.send_json({"type": "thinking", "data": event.text})
                    elif isinstance(event, ToolStart):
                        try:
                            inputs_safe = json.loads(json.dumps(event.inputs, default=str))
                        except Exception:
                            inputs_safe = {"raw": str(event.inputs)}
                        await websocket.send_json({"type": "tool_start", "data": {"name": event.name, "inputs": inputs_safe}})
                    elif isinstance(event, ToolEnd):
                        result_str = str(event.result)[:500]
                        await websocket.send_json({"type": "tool_end", "data": {"name": event.name, "result": result_str, "permitted": event.permitted}})
                    elif isinstance(event, TurnDone):
                        await websocket.send_json({"type": "turn_done", "data": {"input_tokens": event.input_tokens, "output_tokens": event.output_tokens}})
                    elif isinstance(event, PermissionRequest):
                        event.granted = True
                        await websocket.send_json({"type": "permission", "data": {"description": event.description, "auto_approved": True}})
            except Exception as e:
                tb = traceback.format_exc()
                print(f"[WS] Stream error: {tb}")
                try:
                    await websocket.send_json({"type": "error", "data": f"Stream error: {type(e).__name__}: {e}"})
                except Exception:
                    pass
            if full_text and conv_id:
                await db.add_message(conv_id, "assistant", full_text)
            try:
                await websocket.send_json({"type": "done", "data": {"full_text": full_text}})
            except Exception:
                pass
    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Unexpected error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8765))
    print(f"[Arcade OS] Starting on http://127.0.0.1:{port}")
    uvicorn.run("server:app", host="127.0.0.1", port=port, reload=False, log_level="info")

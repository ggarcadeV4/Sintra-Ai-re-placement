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

# ── Ensure project root is on sys.path ─────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import db
from config import load_config

# ── Default system prompt for the GUI ──────────────────────────────────────
DEFAULT_SYSTEM_PROMPT = """You are Arcade OS, a helpful AI assistant running locally on the user's machine.
You are part of a personal business operating system. Be concise, friendly, and action-oriented.
When the user asks you to do something, do it. When they ask a question, answer it directly.
You have access to tools for reading/writing files, running commands, and searching the web."""

# ── Lazy agent imports (avoids crashing server if tools fail to load) ──────

_agent_loaded = False
_agent_error = None

def _ensure_agent():
    """Lazy-load agent module — so server starts even if agent has import issues."""
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

# ── Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hook."""
    # Initialize DB singleton on startup
    await db.get_db()
    print(f"[Arcade OS] Database ready at {db.DB_PATH}")

    # Try to load agent now (but don't crash if it fails)
    _ensure_agent()

    print("[Arcade OS] Server running — open http://127.0.0.1:8765")
    yield
    # Clean shutdown
    await db.close_db()
    print("[Arcade OS] Shutting down.")


app = FastAPI(title="Arcade OS", lifespan=lifespan)

# ── Static files (Stitch exports = the GUI) ────────────────────────────────
STITCH_DIR = PROJECT_ROOT / "stitch_exports"

app.mount("/stitch_exports", StaticFiles(directory=str(STITCH_DIR)), name="stitch")

@app.get("/")
async def index():
    """Serve the unified shell as the root page."""
    return FileResponse(str(STITCH_DIR / "session1_unified_shell.html"))


# ── Health ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Check server + Ollama + agent status."""
    cfg = load_config()
    configured_model = cfg.get("model", "ollama/gemma4")

    # Check if Ollama is reachable
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

    # Resolve which model will actually be used
    resolved_model = await _resolve_model(configured_model) if ollama_ok else configured_model

    return {
        "status": "ok",
        "model": resolved_model,
        "configured_model": configured_model,
        "ollama_connected": ollama_ok,
        "ollama_models": ollama_models,
        "agent_loaded": _agent_error is None if _agent_loaded else "pending",
        "agent_error": _agent_error,
    }


@app.get("/api/models")
async def list_models():
    """Return all available Ollama models for the model switcher."""
    models = await _get_ollama_models()
    # Also include any Gemini models if API key is set
    cfg = load_config()
    extras = []
    if cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY"):
        extras.append({"id": "gemini/gemini-2.5-flash", "name": "Gemini 2.5 Flash", "provider": "gemini"})
        extras.append({"id": "gemini/gemini-2.5-pro", "name": "Gemini 2.5 Pro", "provider": "gemini"})

    # Format Ollama models
    ollama_list = []
    for m in models:
        ollama_list.append({"id": f"ollama/{m}", "name": m, "provider": "ollama"})

    return {"models": ollama_list + extras}


# ── Conversations REST ────────────────────────────────────────────────────

@app.get("/api/conversations")
async def list_conversations():
    convs = await db.list_conversations()
    return convs


@app.post("/api/conversations")
async def create_conversation():
    conv = await db.create_conversation()
    return conv


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

# ── Model Auto-Detection ───────────────────────────────────────────────────

# Preferred models in fallback order
_MODEL_PREFERENCES = ["gemma4", "gemma3", "phi4-mini", "llama3.2", "qwen2.5-coder", "mistral"]

async def _get_ollama_models() -> list[str]:
    """Query Ollama for available models."""
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
    """
    If the configured model is available in Ollama, use it.
    Otherwise, find the best available model from the preference list.
    Non-Ollama models (gemini/, openai/, etc.) are returned as-is.
    """
    # Non-Ollama models don't need resolution
    if not configured_model.startswith("ollama/"):
        return configured_model

    short_name = configured_model.replace("ollama/", "")
    available = await _get_ollama_models()

    if not available:
        print(f"[Model] WARNING: Ollama not reachable, using configured model: {configured_model}")
        return configured_model

    print(f"[Model] Ollama has: {', '.join(available)}")

    # Check if configured model is available (exact or prefix match)
    for m in available:
        if m == short_name or m.startswith(short_name.split(":")[0]):
            resolved = f"ollama/{m}"
            if resolved != configured_model:
                print(f"[Model] Resolved {configured_model} \u2192 {resolved}")
            return resolved

    # Configured model not found — try preference list
    for pref in _MODEL_PREFERENCES:
        for m in available:
            if m.startswith(pref):
                print(f"[Model] {short_name} not found, falling back to: ollama/{m}")
                return f"ollama/{m}"

    # Last resort: use whatever is first available
    if available:
        fallback = f"ollama/{available[0]}"
        print(f"[Model] Using first available model: {fallback}")
        return fallback

    print(f"[Model] No models found in Ollama! Using configured: {configured_model}")
    return configured_model


# ── WebSocket Chat ─────────────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat.

    Client sends:  {"conversation_id": "...", "message": "..."}
    Server sends:  {"type": "text_chunk"|"tool_start"|"tool_end"|"turn_done"|"done"|"error", "data": ...}
    """
    await websocket.accept()
    print("[WS] Client connected")

    # Check if agent is available
    if not _ensure_agent():
        await websocket.send_json({
            "type": "error",
            "data": f"Agent module failed to load: {_agent_error}"
        })
        await websocket.close()
        return

    # Each connection gets its own state — thread safety per the build plan
    agent_state = AgentState()
    cfg = load_config()
    _history_loaded = False  # Flag: only hydrate from DB once per WS connection

    # Use the model from config (user's preference)
    if "model" not in cfg:
        cfg["model"] = "ollama/gemma4"

    # Auto-detect: if configured model isn't available, fall back to what Ollama has
    cfg["model"] = await _resolve_model(cfg["model"])

    # Set permission mode to accept-all for GUI (approval gates come in Phase 6)
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
            model_override = payload.get("model")  # Per-message model switch

            if not user_message:
                await websocket.send_json({"type": "error", "data": "Empty message"})
                continue

            # ── Slice 2: Memory Injection ──────────────────────────────────
            # On the first message of this WS connection, hydrate AgentState
            # with prior conversation history from the database so the AI
            # has full context of previous turns.
            if conv_id and not _history_loaded:
                try:
                    db_messages = await db.get_messages(conv_id)
                    if db_messages:
                        agent_state.messages = [
                            {"role": msg["role"], "content": msg["content"]}
                            for msg in db_messages
                        ]
                        print(f"[WS] Hydrated {len(db_messages)} messages from conv {conv_id}")
                except Exception as e:
                    print(f"[WS] WARNING: Failed to load history: {e}")
                _history_loaded = True

            # Apply model override if provided
            if model_override and model_override != cfg["model"]:
                cfg["model"] = model_override
                print(f"[WS] Model switched to: {cfg['model']}")
                # Reset agent state for new model (different context)
                agent_state = AgentState()
                _history_loaded = False  # Re-hydrate on next message if model switches

            print(f"[WS] User message ({cfg['model']}): {user_message[:80]}...")

            # Persist user message
            if conv_id:
                await db.add_message(conv_id, "user", user_message)
                conv = await db.get_conversation(conv_id)
                if conv and conv["title"] == "New Chat":
                    title = user_message[:60] + ("..." if len(user_message) > 60 else "")
                    await db.update_conversation_title(conv_id, title)

            # ── Stream agent response via threaded queue ───────────────────
            loop = asyncio.get_running_loop()
            event_queue: asyncio.Queue = asyncio.Queue()

            def _threaded_agent():
                """Run the synchronous agent generator in a background thread."""
                try:
                    print(f"[Agent] Starting generation with model {cfg['model']}...")
                    event_count = 0
                    for event in agent_run(
                        user_message=user_message,
                        state=agent_state,
                        config=cfg,
                        system_prompt=DEFAULT_SYSTEM_PROMPT,
                    ):
                        event_count += 1
                        asyncio.run_coroutine_threadsafe(
                            event_queue.put(event), loop
                        ).result(timeout=10)  # Block until queued
                    print(f"[Agent] Generation complete — {event_count} events")
                except Exception as e:
                    tb = traceback.format_exc()
                    print(f"[Agent] ERROR in generation:\n{tb}")
                    asyncio.run_coroutine_threadsafe(
                        event_queue.put(("ERROR", f"{type(e).__name__}: {e}")), loop
                    ).result(timeout=10)
                finally:
                    # Always signal completion
                    asyncio.run_coroutine_threadsafe(
                        event_queue.put(None), loop
                    ).result(timeout=10)

            # Start agent in background thread
            loop.run_in_executor(None, _threaded_agent)

            # Consume events from queue and send to WebSocket
            full_text = ""
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(event_queue.get(), timeout=120)
                    except asyncio.TimeoutError:
                        print("[WS] Agent timeout — no events for 120s")
                        await websocket.send_json({
                            "type": "error",
                            "data": "Response timed out. Is your AI model running? Check that Ollama is started."
                        })
                        break

                    if event is None:
                        break  # Agent finished

                    if isinstance(event, tuple) and len(event) == 2 and event[0] == "ERROR":
                        await websocket.send_json({"type": "error", "data": event[1]})
                        break

                    if isinstance(event, TextChunk):
                        full_text += event.text
                        await websocket.send_json({
                            "type": "text_chunk", "data": event.text
                        })

                    elif isinstance(event, ThinkingChunk):
                        await websocket.send_json({
                            "type": "thinking", "data": event.text
                        })

                    elif isinstance(event, ToolStart):
                        # Safely serialize inputs
                        try:
                            inputs_safe = json.loads(json.dumps(event.inputs, default=str))
                        except Exception:
                            inputs_safe = {"raw": str(event.inputs)}
                        await websocket.send_json({
                            "type": "tool_start",
                            "data": {"name": event.name, "inputs": inputs_safe}
                        })

                    elif isinstance(event, ToolEnd):
                        result_str = str(event.result)[:500]
                        await websocket.send_json({
                            "type": "tool_end",
                            "data": {
                                "name": event.name,
                                "result": result_str,
                                "permitted": event.permitted,
                            }
                        })

                    elif isinstance(event, TurnDone):
                        await websocket.send_json({
                            "type": "turn_done",
                            "data": {
                                "input_tokens": event.input_tokens,
                                "output_tokens": event.output_tokens,
                            }
                        })

                    elif isinstance(event, PermissionRequest):
                        event.granted = True
                        await websocket.send_json({
                            "type": "permission",
                            "data": {"description": event.description, "auto_approved": True}
                        })

            except Exception as e:
                tb = traceback.format_exc()
                print(f"[WS] Stream error: {tb}")
                try:
                    await websocket.send_json({
                        "type": "error",
                        "data": f"Stream error: {type(e).__name__}: {e}"
                    })
                except Exception:
                    pass

            # Persist assistant response
            if full_text and conv_id:
                await db.add_message(conv_id, "assistant", full_text)

            # Send completion signal
            try:
                await websocket.send_json({
                    "type": "done",
                    "data": {"full_text": full_text}
                })
            except Exception:
                pass

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Unexpected error: {e}")
        traceback.print_exc()


# ── Run directly ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8765))
    print(f"[Arcade OS] Starting on http://127.0.0.1:{port}")
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        log_level="info",
    )

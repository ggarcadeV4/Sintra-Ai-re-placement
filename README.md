# Sintra-Ai-re-placement (Arcade OS)

AI-powered content orchestration and social media automation platform.

## Quick Start
```bash
# Install dependencies
pip install -r requirements.txt

# Start the GUI server
python server.py
# Opens at http://127.0.0.1:8765
```

## Architecture
- `server.py` — FastAPI WebSocket server (GUI backend)
- `agent.py` — Multi-turn agent loop with tool execution
- `providers.py` — Multi-provider LLM abstraction (Ollama, Gemini, Anthropic, OpenAI)
- `config.py` — Configuration management
- `db.py` — SQLite conversation persistence
- `context.py` — System prompt builder
- `tools.py` — Built-in tool implementations
- `memory/` — Persistent file-based memory system
- `multi_agent/` — Sub-agent orchestration
- `stitch_exports/` — GUI HTML screens

## Status
Phase 1 in progress — wiring agentic backend to GUI shell.

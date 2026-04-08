"""SQLite persistence layer for Arcade OS conversations."""
import aiosqlite
import uuid
import time
import asyncio
from pathlib import Path

DB_PATH = Path.home() / ".nano_claude" / "arcade_os.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'New Chat',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL DEFAULT '',
    created_at      REAL NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);
"""

_db = None
_db_lock = asyncio.Lock()

async def get_db():
    global _db
    if _db is not None:
        try:
            await _db.execute("SELECT 1")
            return _db
        except Exception:
            _db = None
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _db.executescript(SCHEMA)
    print(f"[DB] Connected to {DB_PATH}")
    return _db

async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None

async def create_conversation(title="New Chat"):
    async with _db_lock:
        db = await get_db()
        conv_id = uuid.uuid4().hex[:16]
        now = time.time()
        await db.execute("INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)", (conv_id, title, now, now))
        await db.commit()
        return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}

async def list_conversations(limit=50):
    async with _db_lock:
        db = await get_db()
        cursor = await db.execute("SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?", (limit,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_conversation(conv_id):
    async with _db_lock:
        db = await get_db()
        cursor = await db.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?", (conv_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def delete_conversation(conv_id):
    async with _db_lock:
        db = await get_db()
        await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        cursor = await db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        await db.commit()
        return cursor.rowcount > 0

async def update_conversation_title(conv_id, title):
    async with _db_lock:
        db = await get_db()
        await db.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (title, time.time(), conv_id))
        await db.commit()

async def touch_conversation(conv_id):
    async with _db_lock:
        db = await get_db()
        await db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (time.time(), conv_id))
        await db.commit()

async def add_message(conv_id, role, content):
    async with _db_lock:
        db = await get_db()
        msg_id = uuid.uuid4().hex[:16]
        now = time.time()
        await db.execute("INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)", (msg_id, conv_id, role, content, now))
        await db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
        await db.commit()
        return {"id": msg_id, "role": role, "content": content, "created_at": now}

async def get_messages(conv_id):
    async with _db_lock:
        db = await get_db()
        cursor = await db.execute("SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at", (conv_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

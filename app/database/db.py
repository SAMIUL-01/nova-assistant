"""
SQLite data layer.

Uses Python's built-in sqlite3 module -- no ORM, no extra dependency.
All SQL lives in this file. Routes never write SQL themselves.

Tables:
    conversations / messages   the chats
    memories                   long-term facts about the user (all chats)
    documents / doc_chunks     uploaded files, split for retrieval
"""

import logging
import sqlite3
from contextlib import contextmanager
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Raised when the database cannot complete an operation."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL DEFAULT 'New Chat',
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role            TEXT    NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages (conversation_id, id);

-- Long-term memory: facts the assistant knows about you, across every chat.
CREATE TABLE IF NOT EXISTS memories (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    content              TEXT    NOT NULL UNIQUE,
    source               TEXT    NOT NULL DEFAULT 'auto',
    pinned               INTEGER NOT NULL DEFAULT 0,
    source_conversation  INTEGER,
    created_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Uploaded files.
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    filename        TEXT    NOT NULL,
    media_type      TEXT    NOT NULL DEFAULT '',
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    text_chars      INTEGER NOT NULL DEFAULT 0,
    stored_path     TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS doc_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    idx         INTEGER NOT NULL,
    content     TEXT    NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON doc_chunks (document_id, idx);
CREATE INDEX IF NOT EXISTS idx_docs_conversation ON documents (conversation_id);
"""


@contextmanager
def get_conn():
    """
    Open a short-lived connection. Commits on success, rolls back on error.

    A fresh connection per operation keeps things safe when FastAPI runs
    endpoints in different worker threads.
    """
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # If the database file is missing (first run, or someone deleted it to
    # reset their chats while the server was running), rebuild the tables.
    needs_schema = not settings.DB_PATH.exists()

    conn = sqlite3.connect(settings.DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        if needs_schema:
            conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        logger.exception("Database error: %s", exc)
        raise DatabaseError(str(exc)) from exc
    finally:
        conn.close()


def init_db() -> None:
    """
    Create any missing tables. Safe to run on every startup, and safe on an
    existing database from an older version (every statement uses IF NOT EXISTS).
    """
    with get_conn() as conn:
        conn.executescript(SCHEMA)
    logger.info("Database ready at %s", settings.DB_PATH)


# --------------------------------------------------------------------------
# Conversations
# --------------------------------------------------------------------------
def create_conversation(title: str = "New Chat") -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (title) VALUES (?)", (title.strip() or "New Chat",)
        )
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return dict(row)


def list_conversations() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id,
                   c.title,
                   c.created_at,
                   c.updated_at,
                   (SELECT COUNT(*) FROM messages m
                     WHERE m.conversation_id = c.id) AS message_count
            FROM conversations c
            ORDER BY c.updated_at DESC, c.id DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_conversation(conversation_id: int) -> Optional[dict]:
    """Return the conversation with all of its messages, or None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if row is None:
            return None
        msgs = conn.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()

    data = dict(row)
    data["messages"] = [dict(m) for m in msgs]
    return data


def conversation_exists(conversation_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    return row is not None


def rename_conversation(conversation_id: int, title: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (title.strip()[:80] or "New Chat", conversation_id),
        )


def touch_conversation(conversation_id: int) -> None:
    """Bump updated_at so the conversation floats to the top of the sidebar."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )


def delete_conversation(conversation_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        deleted = cur.rowcount > 0
        # Explicit cleanup in case the SQLite build ignores ON DELETE CASCADE.
        conn.execute(
            "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
        )
        conn.execute(
            """
            DELETE FROM doc_chunks WHERE document_id IN
                (SELECT id FROM documents WHERE conversation_id = ?)
            """,
            (conversation_id,),
        )
        conn.execute(
            "DELETE FROM documents WHERE conversation_id = ?", (conversation_id,)
        )
    return deleted


# --------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------
def add_message(conversation_id: int, role: str, content: str) -> dict:
    if role not in ("user", "assistant"):
        raise DatabaseError(f"Invalid role: {role}")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conversation_id, role, content),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )
        row = conn.execute(
            "SELECT id, role, content, created_at FROM messages WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return dict(row)


def get_history(conversation_id: int, limit: int = None) -> list:
    """
    Return the most recent messages for a conversation in chronological order.

    This is what gives the AI its memory of the current conversation.
    """
    limit = limit or settings.HISTORY_LIMIT
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM (
                SELECT id, role, content
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) ORDER BY id ASC
            """,
            (conversation_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def count_messages(conversation_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
    return int(row["n"])


# --------------------------------------------------------------------------
# Long-term memories (shared across every conversation)
# --------------------------------------------------------------------------
def list_memories() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, content, source, pinned, source_conversation, created_at
            FROM memories
            ORDER BY pinned DESC, id ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def add_memory(
    content: str,
    source: str = "auto",
    pinned: int = 0,
    source_conversation: int = None,
) -> Optional[dict]:
    """Insert a fact. Returns None if the exact fact is already stored."""
    content = (content or "").strip()
    if not content:
        return None
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO memories (content, source, pinned, source_conversation)
            VALUES (?, ?, ?, ?)
            """,
            (content, source, 1 if pinned else 0, source_conversation),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT id, content, source, pinned, source_conversation, created_at "
            "FROM memories WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return dict(row)


def delete_memory(memory_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    return cur.rowcount > 0


def clear_memories() -> int:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM memories")
    return cur.rowcount


def count_memories() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM memories").fetchone()
    return int(row["n"])


# --------------------------------------------------------------------------
# Documents and their chunks
# --------------------------------------------------------------------------
def add_document(
    conversation_id: Optional[int],
    filename: str,
    media_type: str,
    size_bytes: int,
    chunks: list,
    stored_path: str = "",
) -> dict:
    text_chars = sum(len(c) for c in chunks)
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO documents
                (conversation_id, filename, media_type, size_bytes, text_chars, stored_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conversation_id, filename, media_type, size_bytes, text_chars, stored_path),
        )
        doc_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO doc_chunks (document_id, idx, content) VALUES (?, ?, ?)",
            [(doc_id, i, c) for i, c in enumerate(chunks)],
        )
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    data = dict(row)
    data["chunk_count"] = len(chunks)
    return data


def list_documents(conversation_id: Optional[int] = None) -> list:
    with get_conn() as conn:
        if conversation_id is None:
            rows = conn.execute(
                """
                SELECT d.*, (SELECT COUNT(*) FROM doc_chunks c
                              WHERE c.document_id = d.id) AS chunk_count
                FROM documents d ORDER BY d.id DESC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT d.*, (SELECT COUNT(*) FROM doc_chunks c
                              WHERE c.document_id = d.id) AS chunk_count
                FROM documents d
                WHERE d.conversation_id = ? OR d.conversation_id IS NULL
                ORDER BY d.id DESC
                """,
                (conversation_id,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_document(document_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
    return dict(row) if row else None


def get_chunks_for_conversation(conversation_id: Optional[int]) -> list:
    """Every chunk visible to a conversation (its own docs plus global docs)."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.idx, c.content, d.filename, d.id AS document_id
            FROM doc_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.conversation_id = ? OR d.conversation_id IS NULL
            ORDER BY d.id DESC, c.idx ASC
            """,
            (conversation_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_document(document_id: int) -> Optional[str]:
    """Delete a document and its chunks. Returns the stored file path, if any."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT stored_path FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM doc_chunks WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    return row["stored_path"]

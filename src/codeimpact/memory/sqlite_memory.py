"""Simple SQLite-backed long-term memory store."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
import re


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass(slots=True)
class MemoryRecord:
    id: int
    namespace: str
    memory_type: str
    content: str
    source: str | None
    metadata: dict
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class SQLiteMemoryStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_namespace_type_updated ON memories(namespace, memory_type, updated_at DESC)")

    def store(self, namespace: str, content: str, memory_type: str = "general", source: str | None = None, metadata: dict | None = None) -> int:
        timestamp = _utc_now()
        payload = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO memories(namespace, memory_type, content, source, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (namespace, memory_type, content, source, payload, timestamp, timestamp),
            )
            return int(cursor.lastrowid)

    def recall(self, namespace: str, query: str | None = None, memory_type: str | None = None, limit: int = 5) -> list[MemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, namespace, memory_type, content, source, metadata_json, created_at, updated_at
                FROM memories
                WHERE namespace = ?
                  AND (? IS NULL OR memory_type = ?)
                ORDER BY updated_at DESC, id DESC
                """,
                (namespace, memory_type, memory_type),
            ).fetchall()

        records = [self._row_to_record(row) for row in rows]
        if query:
            records.sort(key=lambda record: (_score_record(query, record.content), record.updated_at), reverse=True)
        return records[:limit]

    def consolidate(self, namespace: str, memory_type: str | None = None) -> int:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, content, memory_type
                FROM memories
                WHERE namespace = ?
                  AND (? IS NULL OR memory_type = ?)
                ORDER BY updated_at DESC, id DESC
                """,
                (namespace, memory_type, memory_type),
            ).fetchall()

            seen: set[tuple[str, str]] = set()
            removed = 0
            for row in rows:
                key = (row["memory_type"], _normalize_text(row["content"]))
                if key in seen:
                    conn.execute("DELETE FROM memories WHERE id = ?", (row["id"],))
                    removed += 1
                else:
                    seen.add(key)
            return removed

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=int(row["id"]),
            namespace=row["namespace"],
            memory_type=row["memory_type"],
            content=row["content"],
            source=row["source"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


def _score_record(query: str, content: str) -> int:
    query_tokens = set(_TOKEN_RE.findall(query.lower()))
    content_tokens = set(_TOKEN_RE.findall(content.lower()))
    score = len(query_tokens & content_tokens)
    if query.lower() in content.lower():
        score += 5
    return score
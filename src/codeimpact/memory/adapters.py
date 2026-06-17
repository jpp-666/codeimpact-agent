"""Memory backend selection."""

from __future__ import annotations

from pathlib import Path

from .sqlite_memory import SQLiteMemoryStore


def create_memory_store(db_path: str | Path) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(db_path)

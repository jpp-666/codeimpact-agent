"""SQLite FTS indexing for CodeImpact RAG context."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
from typing import Iterable

from .chunker import Chunk, iter_repo_chunks


def default_context_db_path(repo_root: str | Path) -> Path:
    repo_root = Path(repo_root).resolve()
    digest = hashlib.sha1(str(repo_root).encode("utf-8")).hexdigest()[:16]
    cache_dir = Path(tempfile.gettempdir()) / "codeimpact-context"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{digest}.sqlite3"


def fts5_available() -> bool:
    try:
        with sqlite3.connect(":memory:") as conn:
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        return True
    except sqlite3.OperationalError:
        return False


def build_index(repo_root: str | Path, db_path: str | Path | None = None) -> dict:
    repo_root = Path(repo_root).resolve()
    db_path = Path(db_path) if db_path is not None else default_context_db_path(repo_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    repo_fingerprint = fingerprint_repo(repo_root)
    chunks = iter_repo_chunks(repo_root)

    with sqlite3.connect(db_path) as conn:
        if not _create_schema(conn):
            return {
                "backend": "fallback",
                "db_path": str(db_path),
                "chunk_count": len(chunks),
                "repo_fingerprint": repo_fingerprint,
                "indexed_at": time.time(),
            }
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM chunks_fts")
        for chunk in chunks:
            index_chunk(conn, chunk)
        conn.execute("CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("DELETE FROM index_meta")
        conn.execute("INSERT INTO index_meta(key, value) VALUES (?, ?)", ("repo", str(repo_root)))
        conn.execute("INSERT INTO index_meta(key, value) VALUES (?, ?)", ("repo_fingerprint", repo_fingerprint))
        conn.execute("INSERT INTO index_meta(key, value) VALUES (?, ?)", ("built_at", str(time.time())))

    return {
        "backend": "fts5",
        "db_path": str(db_path),
        "chunk_count": len(chunks),
        "repo_fingerprint": repo_fingerprint,
        "indexed_at": time.time(),
    }


def ensure_index(repo_root: str | Path, db_path: str | Path | None = None) -> dict:
    repo_root = Path(repo_root).resolve()
    db_path = Path(db_path) if db_path is not None else default_context_db_path(repo_root)
    current_fingerprint = fingerprint_repo(repo_root)
    if db_path.exists() and _has_index(db_path):
        meta = _load_index_meta(db_path)
        if meta.get("repo_fingerprint") == current_fingerprint:
            return {
                "backend": "fts5" if fts5_available() else "fallback",
                "db_path": str(db_path),
                "chunk_count": _count_chunks(db_path),
                "repo_fingerprint": current_fingerprint,
                "indexed_at": float(meta.get("built_at", "0") or 0.0),
            }
    return build_index(repo_root, db_path)


def index_chunk(conn: sqlite3.Connection, chunk: Chunk) -> int:
    cursor = conn.execute(
        """
        INSERT INTO chunks(repo, path, chunk_type, symbol, start_line, end_line, content, snippet)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk.repo,
            chunk.path,
            chunk.chunk_type,
            chunk.symbol,
            chunk.start_line,
            chunk.end_line,
            chunk.content,
            chunk.snippet,
        ),
    )
    rowid = int(cursor.lastrowid)
    conn.execute(
        """
        INSERT INTO chunks_fts(rowid, repo, path, chunk_type, symbol, content)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (rowid, chunk.repo, chunk.path, chunk.chunk_type, chunk.symbol, chunk.content),
    )
    return rowid


def _create_schema(conn: sqlite3.Connection) -> bool:
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chunks (
              id INTEGER PRIMARY KEY,
              repo TEXT NOT NULL,
              path TEXT NOT NULL,
              chunk_type TEXT NOT NULL,
              symbol TEXT NOT NULL,
              start_line INTEGER NOT NULL,
              end_line INTEGER NOT NULL,
              content TEXT NOT NULL,
              snippet TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(repo, path, chunk_type, symbol, content);
            """
        )
        return True
    except sqlite3.OperationalError:
        return False


def _has_index(db_path: Path) -> bool:
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("SELECT 1 FROM chunks LIMIT 1")
            conn.execute("SELECT 1 FROM chunks_fts LIMIT 1")
        return True
    except sqlite3.Error:
        return False


def _count_chunks(db_path: Path) -> int:
    try:
        with sqlite3.connect(db_path) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    except sqlite3.Error:
        return 0


def _load_index_meta(db_path: Path) -> dict[str, str]:
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT key, value FROM index_meta").fetchall()
    except sqlite3.Error:
        return {}
    return {row["key"]: row["value"] for row in rows}


def fingerprint_repo(repo_root: str | Path) -> str:
    repo_root = Path(repo_root).resolve()
    payload: list[dict[str, object]] = []
    for path in _iter_indexable_files(repo_root):
        try:
            stat = path.stat()
            content_hash = hashlib.sha1(path.read_bytes()).hexdigest()
        except OSError:
            continue
        payload.append(
            {
                "path": str(path.resolve().relative_to(repo_root)),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha1": content_hash,
            }
        )
    raw = json.dumps(sorted(payload, key=lambda item: item["path"]), ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _iter_indexable_files(repo_root: Path) -> Iterable[Path]:
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.parts if part not in {".", ".."}):
            continue
        if any(part in {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".venv", "venv", "env", "dist", "build"} for part in path.parts):
            continue
        suffix = path.suffix.lower()
        if suffix == ".py":
            yield path
        elif suffix in {".md", ".rst", ".txt"} and (path.name.lower() in {"readme.md", "readme.rst"} or any(part == "docs" for part in path.parts)):
            yield path

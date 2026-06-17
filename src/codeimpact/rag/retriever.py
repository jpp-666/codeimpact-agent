"""Context retrieval over code/test/docs chunks."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
import time
from typing import Iterable

from codeimpact.ast_graph import RelatedFile
from codeimpact.diff_parser import GitDiff

from .chunker import Chunk, iter_repo_chunks
from .indexer import default_context_db_path, ensure_index


_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STOP_TOKENS = {
    "and",
    "as",
    "class",
    "def",
    "else",
    "false",
    "for",
    "from",
    "if",
    "import",
    "in",
    "is",
    "none",
    "or",
    "pass",
    "return",
    "true",
    "with",
}


@dataclass(slots=True)
class ContextHit:
    path: str
    chunk_type: str
    symbol: str
    start_line: int
    end_line: int
    score: float
    snippet: str

    def to_dict(self, repo_root: str | Path | None = None) -> dict:
        path = Path(self.path)
        if repo_root is not None:
            try:
                path_value = path.resolve().relative_to(Path(repo_root).resolve()).as_posix()
            except ValueError:
                path_value = path.as_posix()
        else:
            path_value = path.as_posix()
        return {
            "path": path_value,
            "chunk_type": self.chunk_type,
            "symbol": self.symbol,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "score": round(self.score, 4),
            "snippet": self.snippet,
        }


@dataclass(slots=True)
class ContextRetrievalResult:
    query: str
    hits: list[ContextHit]
    retrieval_ms: float
    backend: str


class CodeContextRetriever:
    def __init__(self, repo_root: str | Path, db_path: str | Path | None = None):
        self.repo_root = Path(repo_root).resolve()
        self.db_path = Path(db_path) if db_path is not None else default_context_db_path(self.repo_root)
        self.index_info = ensure_index(self.repo_root, self.db_path)
        self.backend = str(self.index_info.get("backend", "fallback"))
        self._fallback_chunks: list[Chunk] | None = None

    def search(self, query: str, top_k: int = 5, exclude_paths: Iterable[str | Path] | None = None) -> ContextRetrievalResult:
        start = time.perf_counter()
        exclude = _normalize_exclude_paths(self.repo_root, exclude_paths or [])
        if self.backend == "fts5":
            try:
                hits = self._search_fts(query, top_k=top_k, exclude_paths=exclude)
            except sqlite3.Error:
                hits = self._search_fallback(query, top_k=top_k, exclude_paths=exclude)
        else:
            hits = self._search_fallback(query, top_k=top_k, exclude_paths=exclude)
        hits = _dedupe_hits_by_path(hits)[:top_k]
        return ContextRetrievalResult(
            query=query,
            hits=hits,
            retrieval_ms=round((time.perf_counter() - start) * 1000, 3),
            backend=self.backend,
        )

    def _search_fts(self, query: str, top_k: int, exclude_paths: set[str]) -> list[ContextHit]:
        tokens = _tokenize(query)
        if not tokens:
            return []
        match_query = " OR ".join(tokens[:24])
        rows: list[ContextHit] = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT
                  c.path,
                  c.chunk_type,
                  c.symbol,
                  c.start_line,
                  c.end_line,
                  1.0 / (1.0 + abs(bm25(chunks_fts))) AS score,
                  c.snippet
                FROM chunks_fts
                JOIN chunks c ON c.id = chunks_fts.rowid
                WHERE chunks_fts MATCH ?
                ORDER BY bm25(chunks_fts)
                LIMIT ?
                """,
                (match_query, top_k * 4),
            )
            for row in cursor.fetchall():
                if str(Path(row["path"]).resolve()) in exclude_paths:
                    continue
                rows.append(
                    ContextHit(
                        path=row["path"],
                        chunk_type=row["chunk_type"],
                        symbol=row["symbol"],
                        start_line=int(row["start_line"]),
                        end_line=int(row["end_line"]),
                        score=_boost_score(float(row["score"]), tokens, row["path"], row["symbol"], row["chunk_type"]),
                        snippet=row["snippet"],
                    )
                )
                if len(rows) >= top_k * 4:
                    break
        rows.sort(key=lambda item: item.score, reverse=True)
        return rows[:top_k]

    def _search_fallback(self, query: str, top_k: int, exclude_paths: set[str]) -> list[ContextHit]:
        if self._fallback_chunks is None:
            self._fallback_chunks = iter_repo_chunks(self.repo_root)
        query_tokens = _tokenize(query)
        hits: list[ContextHit] = []
        for chunk in self._fallback_chunks:
            if str(Path(chunk.path).resolve()) in exclude_paths:
                continue
            tokens = _tokenize(" ".join([chunk.path, chunk.symbol, chunk.chunk_type, chunk.content]))
            score = sum(tokens.count(token) for token in query_tokens)
            if score <= 0:
                continue
            hits.append(
                ContextHit(
                    path=chunk.path,
                    chunk_type=chunk.chunk_type,
                    symbol=chunk.symbol,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    score=_boost_score(float(score), query_tokens, chunk.path, chunk.symbol, chunk.chunk_type),
                    snippet=chunk.snippet,
                )
            )
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:top_k]


def retrieve_context_for_diff(
    repo_root: str | Path,
    git_diff: GitDiff,
    related: list[RelatedFile],
    *,
    top_k: int = 5,
) -> ContextRetrievalResult:
    repo_root = Path(repo_root).resolve()
    query = build_context_query(repo_root, git_diff, related)
    exclude_paths = [repo_root / file.path for file in git_diff.files]
    retriever = CodeContextRetriever(repo_root)
    return retriever.search(query, top_k=top_k, exclude_paths=exclude_paths)


def build_context_query(repo_root: str | Path, git_diff: GitDiff, related: list[RelatedFile]) -> str:
    repo_root = Path(repo_root).resolve()
    tokens: list[str] = []
    for file in git_diff.files:
        path = Path(file.path)
        tokens.extend(_tokenize(" ".join(path.parts)))
        tokens.extend(_extract_top_level_symbols(repo_root / file.path))
        for hunk in file.hunks:
            for line in hunk.lines:
                if line.kind in {"add", "delete"}:
                    tokens.extend(_tokenize(line.content))

    for item in related:
        related_path = Path(item.path)
        tokens.extend(_tokenize(related_path.stem))
        tokens.extend(_tokenize(item.module))
        try:
            tokens.extend(_extract_top_level_symbols(related_path))
        except OSError:
            continue

    return " ".join(_dedupe_tokens(tokens))


def _extract_top_level_symbols(path: Path) -> list[str]:
    if path.suffix.lower() != ".py" or not path.exists():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError):
        return []
    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols.append(target.id)
    return symbols


def _normalize_exclude_paths(repo_root: Path, paths: Iterable[str | Path]) -> set[str]:
    normalized: set[str] = set()
    for path in paths:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        normalized.add(str(candidate.resolve()))
    return normalized


def _tokenize(text: str) -> list[str]:
    tokens = [token.lower() for token in _TOKEN_RE.findall(text)]
    return [token for token in tokens if len(token) > 1 and token not in _STOP_TOKENS]


def _dedupe_tokens(tokens: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        normalized = token.lower()
        if normalized in seen or normalized in _STOP_TOKENS or len(normalized) <= 1:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:32]


def _boost_score(base_score: float, query_tokens: list[str], path: str, symbol: str, chunk_type: str) -> float:
    score = base_score
    query_set = set(query_tokens)
    if chunk_type == "test" or "tests" in Path(path).parts:
        score += 0.15
    if query_set & set(_tokenize(Path(path).stem)):
        score += 0.08
    if query_set & set(_tokenize(symbol)):
        score += 0.08
    return score


def _dedupe_hits_by_path(hits: list[ContextHit]) -> list[ContextHit]:
    best: dict[str, ContextHit] = {}
    for hit in hits:
        key = str(Path(hit.path).resolve())
        previous = best.get(key)
        if previous is None or hit.score > previous.score:
            best[key] = hit
    return sorted(best.values(), key=lambda item: item.score, reverse=True)

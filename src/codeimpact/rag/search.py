"""Lightweight retrieval over repo text artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
import re
from typing import Iterable


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_TEXT_EXTENSIONS = {".md", ".txt", ".py", ".rst", ".json"}


@dataclass(slots=True)
class SearchHit:
    path: str
    score: float
    snippet: str

    def to_dict(self) -> dict:
        return {"path": self.path, "score": self.score, "snippet": self.snippet}


class LightweightRetriever:
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)
        self.documents = self._load_documents()
        self._doc_tokens = {path: _tokenize(text) for path, text in self.documents.items()}
        self._idf = self._build_idf(self._doc_tokens.values())

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        query_tokens = _tokenize(query)
        hits: list[SearchHit] = []
        for path, text in self.documents.items():
            tokens = self._doc_tokens[path]
            score = _bm25_like_score(query_tokens, tokens, self._idf)
            if score <= 0:
                continue
            hits.append(SearchHit(path=str(path), score=score, snippet=_make_snippet(text, query_tokens)))
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:top_k]

    def _load_documents(self) -> dict[Path, str]:
        docs: dict[Path, str] = {}
        for path in self.repo_root.rglob("*"):
            if not path.is_file():
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            if path.suffix.lower() not in _TEXT_EXTENSIONS:
                continue
            try:
                docs[path] = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
        return docs

    @staticmethod
    def _build_idf(doc_tokens: Iterable[list[str]]) -> dict[str, float]:
        doc_count = 0
        df: dict[str, int] = {}
        for tokens in doc_tokens:
            doc_count += 1
            for token in set(tokens):
                df[token] = df.get(token, 0) + 1
        if doc_count == 0:
            return {}
        return {token: math.log((doc_count + 1) / (freq + 1)) + 1 for token, freq in df.items()}


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _bm25_like_score(query_tokens: list[str], doc_tokens: list[str], idf: dict[str, float]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    tf: dict[str, int] = {}
    for token in doc_tokens:
        tf[token] = tf.get(token, 0) + 1
    score = 0.0
    for token in query_tokens:
        score += tf.get(token, 0) * idf.get(token, 0.0)
    return score / max(1, len(doc_tokens))


def _make_snippet(text: str, query_tokens: list[str], width: int = 180) -> str:
    lowered = text.lower()
    for token in query_tokens:
        idx = lowered.find(token)
        if idx >= 0:
            start = max(0, idx - width // 2)
            end = min(len(text), idx + width // 2)
            return text[start:end].replace("\n", " ").strip()
    return text[:width].replace("\n", " ").strip()

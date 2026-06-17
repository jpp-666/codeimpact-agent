"""Retrieval backend selection."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .search import LightweightRetriever, SearchHit


class Retriever(Protocol):
    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        ...


def create_retriever(repo_root: str | Path) -> Retriever:
    root = Path(repo_root)
    return LightweightRetriever(root)

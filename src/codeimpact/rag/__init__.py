"""Lightweight RAG helpers for CodeImpact Agent."""

from .chunker import Chunk, chunk_markdown_file, chunk_python_file, iter_repo_chunks
from .indexer import build_index, default_context_db_path, ensure_index
from .retriever import CodeContextRetriever, ContextHit, ContextRetrievalResult, build_context_query, retrieve_context_for_diff

__all__ = [
    "Chunk",
    "CodeContextRetriever",
    "ContextHit",
    "ContextRetrievalResult",
    "build_context_query",
    "build_index",
    "chunk_markdown_file",
    "chunk_python_file",
    "default_context_db_path",
    "ensure_index",
    "iter_repo_chunks",
    "retrieve_context_for_diff",
]

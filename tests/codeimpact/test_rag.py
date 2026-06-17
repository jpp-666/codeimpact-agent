from pathlib import Path

from codeimpact.diff_parser import parse_git_diff
from codeimpact.rag.chunker import chunk_markdown_file, chunk_python_file
from codeimpact.rag.indexer import build_index, ensure_index
from codeimpact.rag.retriever import CodeContextRetriever, build_context_query, retrieve_context_for_diff
from codeimpact.ast_graph import build_python_dependency_graph


def test_chunk_python_file_extracts_symbols(tmp_path: Path) -> None:
    path = tmp_path / "pkg.py"
    path.write_text(
        "from x import y\n\n\ndef run():\n    return y()\n\nclass Service:\n    pass\n",
        encoding="utf-8",
    )

    chunks = chunk_python_file(path, tmp_path)

    symbols = {chunk.symbol for chunk in chunks}
    assert "run" in symbols
    assert "Service" in symbols
    assert any(chunk.chunk_type == "module" for chunk in chunks)


def test_chunk_markdown_file_splits_headings(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("# Intro\nhello\n\n## API\nrun()\n", encoding="utf-8")

    chunks = chunk_markdown_file(path, tmp_path)

    assert len(chunks) >= 2
    assert chunks[0].chunk_type == "doc"
    assert any(chunk.symbol == "API" for chunk in chunks)


def test_context_retriever_hits_expected_chunks(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    retriever = CodeContextRetriever(repo)
    diff = parse_git_diff(_core_diff())
    graph = build_python_dependency_graph(repo)
    related = graph.related_files([repo / "pkg/core.py"])
    query = build_context_query(repo, diff, related)

    result = retriever.search(query, top_k=5, exclude_paths=[repo / "pkg/core.py"])
    paths = [Path(hit.path).resolve().relative_to(repo.resolve()).as_posix() for hit in result.hits]

    assert result.backend in {"fts5", "fallback"}
    assert any(path == "tests/test_core.py" for path in paths)
    assert all(path != "pkg/core.py" for path in paths)


def test_retrieve_context_for_diff_returns_metadata(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    diff = parse_git_diff(_core_diff())
    graph = build_python_dependency_graph(repo)
    related = graph.related_files([repo / "pkg/core.py"])

    result = retrieve_context_for_diff(repo, diff, related, top_k=3)

    assert result.hits
    first = result.hits[0].to_dict(repo)
    assert {"path", "chunk_type", "symbol", "score", "snippet"} <= set(first)
    assert result.retrieval_ms >= 0


def test_ensure_index_rebuilds_when_repo_changes(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = tmp_path / "context.sqlite3"

    first = build_index(repo, db_path)
    second = ensure_index(repo, db_path)
    assert first["repo_fingerprint"] == second["repo_fingerprint"]

    (repo / "README.md").write_text("pkg.core.run and tests/test_core.py\nupdated", encoding="utf-8")

    third = ensure_index(repo, db_path)

    assert third["repo_fingerprint"] != first["repo_fingerprint"]
    assert third["chunk_count"] >= first["chunk_count"]


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    pkg = repo / "pkg"
    docs = repo / "docs"
    tests = repo / "tests"
    pkg.mkdir(parents=True)
    docs.mkdir()
    tests.mkdir()
    (pkg / "__init__.py").write_text("from .core import run\n", encoding="utf-8")
    (pkg / "core.py").write_text("from .util import helper\n\n\ndef run():\n    return helper() + 1\n", encoding="utf-8")
    (pkg / "util.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (repo / "README.md").write_text("pkg.core.run and tests/test_core.py", encoding="utf-8")
    (docs / "usage.md").write_text("# Usage\nrun is the public API\n", encoding="utf-8")
    (tests / "test_core.py").write_text("from pkg.core import run\n", encoding="utf-8")
    return repo


def _core_diff() -> str:
    return "\n".join(
        [
            "diff --git a/pkg/core.py b/pkg/core.py",
            "--- a/pkg/core.py",
            "+++ b/pkg/core.py",
            "@@ -1,4 +1,4 @@",
            " from .util import helper",
            "",
            " def run():",
            "-    return helper() + 1",
            "+    return helper() + 2",
        ]
    )

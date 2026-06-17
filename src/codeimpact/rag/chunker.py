"""Chunking helpers for lightweight code/document retrieval."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import ast
from pathlib import Path
import re


_SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
}
_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(slots=True)
class Chunk:
    repo: str
    path: str
    chunk_type: str
    symbol: str
    start_line: int
    end_line: int
    content: str
    snippet: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def chunk_python_file(path: str | Path, repo_root: str | Path | None = None) -> list[Chunk]:
    path = Path(path)
    repo_root = Path(repo_root).resolve() if repo_root is not None else path.parent
    try:
        source = path.read_text(encoding="utf-8-sig")
    except OSError:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [_whole_file_chunk(repo_root, path, source, chunk_type="module", symbol=path.stem)]

    lines = source.splitlines()
    chunks: list[Chunk] = []
    covered_lines: set[int] = set()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start_line = getattr(node, "lineno", 1)
            end_line = getattr(node, "end_lineno", start_line)
            chunks.append(
                _build_chunk(
                    repo_root,
                    path,
                    lines,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type="function" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "class",
                    symbol=node.name,
                )
            )
            covered_lines.update(range(start_line, end_line + 1))

    module_lines = [index + 1 for index, line in enumerate(lines) if line.strip()]
    top_level_lines = [line_no for line_no in module_lines if line_no not in covered_lines]
    if top_level_lines:
        start_line = min(top_level_lines)
        end_line = max(top_level_lines)
        chunks.append(
            _build_chunk(
                repo_root,
                path,
                lines,
                start_line=start_line,
                end_line=end_line,
                chunk_type="module",
                symbol=path.stem,
            )
        )
    elif not chunks:
        chunks.append(_whole_file_chunk(repo_root, path, source, chunk_type="module", symbol=path.stem))

    return chunks


def chunk_markdown_file(path: str | Path, repo_root: str | Path | None = None) -> list[Chunk]:
    path = Path(path)
    repo_root = Path(repo_root).resolve() if repo_root is not None else path.parent
    try:
        source = path.read_text(encoding="utf-8-sig")
    except OSError:
        return []

    lines = source.splitlines()
    sections: list[tuple[int, int, str, str]] = []
    current_start = 1
    current_title = path.stem

    for index, line in enumerate(lines, start=1):
        match = _MARKDOWN_HEADING_RE.match(line)
        if not match:
            continue
        if index > current_start:
            sections.append((current_start, index - 1, current_title, _slice_lines(lines, current_start, index - 1)))
        current_start = index
        current_title = match.group(2).strip()

    if lines:
        sections.append((current_start, len(lines), current_title, _slice_lines(lines, current_start, len(lines))))

    chunks = [
        Chunk(
            repo=str(repo_root),
            path=str(path.resolve()),
            chunk_type="doc",
            symbol=title or path.stem,
            start_line=start,
            end_line=end,
            content=content.strip(),
            snippet=_make_snippet(content),
        )
        for start, end, title, content in sections
        if content.strip()
    ]

    return chunks or [_whole_file_chunk(repo_root, path, source, chunk_type="doc", symbol=path.stem)]


def iter_repo_chunks(repo_root: str | Path) -> list[Chunk]:
    repo_root = Path(repo_root).resolve()
    chunks: list[Chunk] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS or part.startswith(".") for part in path.parts):
            continue
        suffix = path.suffix.lower()
        if suffix == ".py":
            chunks.extend(chunk_python_file(path, repo_root=repo_root))
        elif suffix in {".md", ".rst", ".txt"} and (
            path.name.lower() in {"readme.md", "readme.rst"} or any(part == "docs" for part in path.parts)
        ):
            chunks.extend(chunk_markdown_file(path, repo_root=repo_root))
    return chunks


def _build_chunk(
    repo_root: Path,
    path: Path,
    lines: list[str],
    *,
    start_line: int,
    end_line: int,
    chunk_type: str,
    symbol: str,
) -> Chunk:
    content = _slice_lines(lines, start_line, end_line)
    return Chunk(
        repo=str(repo_root),
        path=str(path.resolve()),
        chunk_type=chunk_type,
        symbol=symbol,
        start_line=start_line,
        end_line=end_line,
        content=content.strip(),
        snippet=_make_snippet(content),
    )


def _whole_file_chunk(repo_root: Path, path: Path, content: str, *, chunk_type: str, symbol: str) -> Chunk:
    return Chunk(
        repo=str(repo_root),
        path=str(path.resolve()),
        chunk_type=chunk_type,
        symbol=symbol,
        start_line=1,
        end_line=max(1, len(content.splitlines())),
        content=content.strip(),
        snippet=_make_snippet(content),
    )


def _slice_lines(lines: list[str], start_line: int, end_line: int) -> str:
    return "\n".join(lines[start_line - 1 : end_line])


def _make_snippet(content: str, width: int = 200) -> str:
    content = content.replace("\n", " ").strip()
    return content if len(content) <= width else f"{content[: width - 3]}..."

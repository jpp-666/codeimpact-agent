
"""Build an AST-based reverse dependency graph for Python repositories."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import ast
from collections import defaultdict, deque
from pathlib import Path
import re
from typing import Iterable


_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "site-packages",
}
_IMPORT_MODULE_RE = re.compile(r"^(?:importlib\.import_module|__import__)$")


@dataclass(slots=True)
class RelatedFile:
    path: str
    module: str
    depth: int
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class PythonDependencyGraph:
    repo_root: Path
    path_to_module: dict[str, str]
    module_to_path: dict[str, str]
    forward_edges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    reverse_edges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def related_files(self, changed_files: Iterable[str | Path], max_depth: int = 2) -> list[RelatedFile]:
        seed_paths = {self._normalize_path(path) for path in changed_files}
        seed_paths = {path for path in seed_paths if path in self.path_to_module}
        queue: deque[tuple[str, int, str]] = deque()
        seen: set[str] = set(seed_paths)
        related: dict[str, RelatedFile] = {}

        for path in seed_paths:
            queue.append((path, 0, "seed"))

        while queue:
            path, depth, _reason = queue.popleft()
            if depth >= max_depth:
                continue
            module = self.path_to_module.get(path)
            if not module:
                continue
            for importer in sorted(self.reverse_edges.get(path, set())):
                if importer in seen:
                    continue
                seen.add(importer)
                importer_module = self.path_to_module.get(importer, "")
                related[importer] = RelatedFile(path=importer, module=importer_module, depth=depth + 1, reason=f"imported by {module}")
                queue.append((importer, depth + 1, f"imported by {module}"))

        return sorted(related.values(), key=lambda item: (item.depth, item.path))

    def to_dict(self) -> dict:
        return {
            "repo_root": str(self.repo_root),
            "path_to_module": self.path_to_module,
            "module_to_path": self.module_to_path,
            "forward_edges": {key: sorted(value) for key, value in self.forward_edges.items()},
            "reverse_edges": {key: sorted(value) for key, value in self.reverse_edges.items()},
        }

    def _normalize_path(self, path: str | Path) -> str:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.repo_root / candidate
        return str(candidate.resolve())


def build_python_dependency_graph(repo_root: str | Path) -> PythonDependencyGraph:
    repo_root = Path(repo_root).resolve()
    module_info: list[tuple[Path, str, ast.AST | None]] = []

    for path in _iter_python_files(repo_root):
        module_name = _path_to_module_name(repo_root, path)
        tree = _parse_ast(path)
        module_info.append((path.resolve(), module_name, tree))

    path_to_module = {str(path): module for path, module, _ in module_info}
    module_to_path = {module: str(path) for path, module, _ in module_info}
    forward_edges: dict[str, set[str]] = defaultdict(set)
    reverse_edges: dict[str, set[str]] = defaultdict(set)

    for path, module_name, tree in module_info:
        source_path = str(path)
        import_targets = _collect_import_targets(tree, module_name, path, module_to_path) if tree is not None else set()
        for target in import_targets:
            resolved = _resolve_module_target(module_to_path, target)
            for target_path in resolved:
                if target_path == source_path:
                    continue
                forward_edges[source_path].add(target_path)
                reverse_edges[target_path].add(source_path)

    return PythonDependencyGraph(repo_root=repo_root, path_to_module=path_to_module, module_to_path=module_to_path, forward_edges=forward_edges, reverse_edges=reverse_edges)


def _iter_python_files(repo_root: Path) -> Iterable[Path]:
    for path in repo_root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        yield path


def _parse_ast(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _path_to_module_name(repo_root: Path, path: Path) -> str:
    relative = path.relative_to(repo_root)
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = Path(parts[-1]).stem
    return ".".join(part for part in parts if part)


def _current_package(module_name: str, path: Path) -> str:
    if path.name == "__init__.py":
        return module_name
    parts = module_name.split(".")
    return ".".join(parts[:-1])


def _resolve_relative(module_name: str, path: Path, level: int, target: str | None) -> str:
    package = _current_package(module_name, path)
    package_parts = package.split(".") if package else []
    if level > len(package_parts) + 1:
        return target or ""
    base_parts = package_parts[: max(0, len(package_parts) - (level - 1))]
    if target:
        base_parts.extend(target.split("."))
    return ".".join(part for part in base_parts if part)


def _collect_import_targets(tree: ast.AST, module_name: str, path: Path, module_to_path: dict[str, str]) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
            continue
        if isinstance(node, ast.ImportFrom):
            base = _resolve_relative(module_name, path, node.level or 0, node.module)
            if base:
                targets.add(base)
            for alias in node.names:
                if alias.name == "*":
                    continue
                if base:
                    targets.add(f"{base}.{alias.name}")
                elif node.level:
                    relative_name = _resolve_relative(module_name, path, node.level, alias.name)
                    if relative_name:
                        targets.add(relative_name)
            continue
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if not _IMPORT_MODULE_RE.match(call_name or ""):
                continue
            if not node.args:
                continue
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                targets.add(first_arg.value)
    if path.name == "__init__.py":
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = _resolve_relative(module_name, path, node.level or 0, node.module)
                if base and base in module_to_path:
                    targets.add(base)
    return {target for target in targets if target}


def _call_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = []
        current: ast.AST | None = func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
    return None


def _resolve_module_target(module_to_path: dict[str, str], target: str) -> set[str]:
    resolved: set[str] = set()
    if target in module_to_path:
        resolved.add(module_to_path[target])
    return resolved

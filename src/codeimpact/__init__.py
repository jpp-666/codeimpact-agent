"""CodeImpact Agent package."""

from .ast_graph import PythonDependencyGraph, build_python_dependency_graph
from .diff_parser import GitDiff, GitFileChange, parse_git_diff
from .memory.sqlite_memory import SQLiteMemoryStore

__all__ = [
    "GitDiff",
    "GitFileChange",
    "PythonDependencyGraph",
    "SQLiteMemoryStore",
    "build_python_dependency_graph",
    "parse_git_diff",
]

__version__ = "0.1.0"
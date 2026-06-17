"""FastMCP server for CodeImpact Agent."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .ast_graph import build_python_dependency_graph
from .diff_parser import parse_git_diff
from .graph import CodeImpactRuntime, create_workflow
from .memory.sqlite_memory import SQLiteMemoryStore
from .report import suggest_tests as build_test_suggestions

mcp = FastMCP("CodeImpactAgent")
_MEMORY = SQLiteMemoryStore(Path(__file__).resolve().parents[2] / "memory.sqlite3")


def _tool(func):
    mcp.tool()(func)
    return func


@_tool
def get_changed_files(diff_text: str) -> list[str]:
    parsed = parse_git_diff(diff_text)
    return [file.path for file in parsed.files]


@_tool
def analyze_diff(repo: str, diff_text: str) -> dict:
    workflow = create_workflow(CodeImpactRuntime(memory=_MEMORY, repo_root=Path(repo)))
    state = workflow.invoke({"repo": repo, "diff_text": diff_text})
    return state.get("report", {})


@_tool
def search_code_context(repo: str, path: str) -> dict:
    graph = build_python_dependency_graph(repo)
    related = graph.related_files([Path(repo) / path])
    return {"path": path, "related_files": [item.to_dict() for item in related]}


@_tool
def suggest_tests(repo: str, diff_text: str) -> dict:
    parsed = parse_git_diff(diff_text)
    graph = build_python_dependency_graph(repo)
    changed_paths = [Path(repo) / file.path for file in parsed.files]
    related = graph.related_files(changed_paths)
    return {
        "changed_files": [file.path for file in parsed.files],
        "related_files": [item.to_dict() for item in related],
        "suggestions": build_test_suggestions(repo, parsed, related),
    }


@_tool
def save_memory(namespace: str, content: str, memory_type: str = "general") -> dict:
    memory_id = _MEMORY.store(namespace, content, memory_type=memory_type)
    return {"id": memory_id}


@_tool
def recall_memory(namespace: str, query: str, memory_type: str | None = None, limit: int = 5) -> dict:
    records = _MEMORY.recall(namespace, query=query, memory_type=memory_type, limit=limit)
    return {"records": [record.to_dict() for record in records]}


async def _list_tools_compat():
    return list((await mcp.get_tools()).values())


async def _call_tool_compat(name: str, arguments: Mapping[str, Any]):
    tool = await mcp.get_tool(name)
    return await tool.run(dict(arguments))


if not hasattr(mcp, "list_tools"):
    mcp.list_tools = _list_tools_compat  # type: ignore[attr-defined]

if not hasattr(mcp, "call_tool"):
    mcp.call_tool = _call_tool_compat  # type: ignore[attr-defined]


if __name__ == "__main__":
    mcp.run()

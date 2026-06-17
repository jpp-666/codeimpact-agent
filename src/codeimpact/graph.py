"""LangGraph orchestration for CodeImpact Agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .ast_graph import RelatedFile, build_python_dependency_graph
from .diff_parser import GitDiff, GitFileChange, GitHunk, parse_git_diff
from .memory.sqlite_memory import SQLiteMemoryStore
from .report import build_basic_report
from .rag.retriever import retrieve_context_for_diff
from .risk import call_risk_model, fallback_risk_assessment


class CodeImpactState(TypedDict, total=False):
    repo: str
    diff_text: str
    parsed_diff: dict
    dependency_graph: dict
    related_files: list[dict]
    retrieved_context: list[dict]
    retrieval_ms: float
    memory_context: list[dict]
    risk_assessment: dict
    deep_analysis: dict
    report: dict


@dataclass(slots=True)
class CodeImpactRuntime:
    memory: SQLiteMemoryStore
    namespace: str = "codeimpact"
    repo_root: Path | None = None
    history: list[dict] = field(default_factory=list)

    def remember(self, memory_type: str, content: str, source: str | None = None) -> int:
        return self.memory.store(self.namespace, content, memory_type=memory_type, source=source)

    def recall(self, query: str, memory_type: str | None = None, limit: int = 5):
        return self.memory.recall(self.namespace, query=query, memory_type=memory_type, limit=limit)


def create_workflow(runtime: CodeImpactRuntime):
    graph = StateGraph(CodeImpactState)

    def parse_node(state: CodeImpactState) -> CodeImpactState:
        parsed = parse_git_diff(state["diff_text"])
        return {"parsed_diff": parsed.to_dict()}

    def dependency_node(state: CodeImpactState) -> CodeImpactState:
        repo = Path(state["repo"])
        graph_obj = build_python_dependency_graph(repo)
        parsed = _git_diff_from_dict(state["parsed_diff"])
        changed = [repo / file.path for file in parsed.files]
        related = graph_obj.related_files(changed)
        return {"dependency_graph": graph_obj.to_dict(), "related_files": [item.to_dict() for item in related]}

    def retrieve_context_node(state: CodeImpactState) -> CodeImpactState:
        parsed = _git_diff_from_dict(state["parsed_diff"])
        related = [RelatedFile(**item) for item in state.get("related_files", [])]
        result = retrieve_context_for_diff(state["repo"], parsed, related, top_k=5)
        repo_root = runtime.repo_root or Path(state["repo"])
        return {
            "retrieved_context": [hit.to_dict(repo_root) for hit in result.hits],
            "retrieval_ms": result.retrieval_ms,
        }

    def reason_risk_node(state: CodeImpactState) -> CodeImpactState:
        parsed = _git_diff_from_dict(state["parsed_diff"])
        related = [RelatedFile(**item) for item in state.get("related_files", [])]
        memory_context = _recall_analysis_memory(runtime, state["repo"], parsed)
        assessed = call_risk_model(
            state["repo"],
            parsed,
            related,
            memory_context=memory_context,
            retrieved_context=state.get("retrieved_context", []),
        )
        if not assessed:
            assessed = fallback_risk_assessment(parsed, related)
        return {"risk_assessment": assessed, "memory_context": memory_context}

    def deep_analysis_node(state: CodeImpactState) -> CodeImpactState:
        related_count = len(state.get("related_files", []))
        changed_count = len(state.get("parsed_diff", {}).get("files", []))
        return {
            "deep_analysis": {
                "trigger": "high risk with broad reverse dependencies",
                "recommendations": [
                    f"Review {changed_count} changed file(s) against {related_count} downstream dependent file(s).",
                    "Run package-level regression tests before merging.",
                    "Ask a human reviewer to inspect public interfaces and re-exported modules.",
                ],
            }
        }

    def report_node(state: CodeImpactState) -> CodeImpactState:
        parsed = _git_diff_from_dict(state["parsed_diff"])
        related = [RelatedFile(**item) for item in state.get("related_files", [])]
        context_sources = ["AST reverse dependency"]
        if state.get("retrieved_context"):
            context_sources.append("RAG retrieved code/test/doc context")
        if state.get("memory_context"):
            context_sources.append("SQLite Memory")
        report = build_basic_report(
            state["repo"],
            parsed,
            related,
            risk_assessment=state.get("risk_assessment"),
            retrieved_context=state.get("retrieved_context", []),
            context_sources=context_sources,
            retrieval_ms=float(state.get("retrieval_ms", 0.0)),
        )
        payload = report.to_dict()
        if state.get("memory_context"):
            payload["memory_context"] = state["memory_context"]
        if state.get("deep_analysis"):
            payload["deep_analysis"] = state["deep_analysis"]
        runtime.remember(
            "analysis",
            json.dumps(payload, ensure_ascii=False),
            source=state["repo"],
        )
        return {"report": payload}

    graph.add_node("parse", parse_node)
    graph.add_node("dependency", dependency_node)
    graph.add_node("retrieve_context", retrieve_context_node)
    graph.add_node("reason_risk", reason_risk_node)
    graph.add_node("deep_analysis", deep_analysis_node)
    graph.add_node("report", report_node)

    graph.add_edge(START, "parse")
    graph.add_edge("parse", "dependency")
    graph.add_edge("dependency", "retrieve_context")
    graph.add_edge("retrieve_context", "reason_risk")
    graph.add_conditional_edges(
        "reason_risk",
        _route_after_risk,
        {"deep_analysis": "deep_analysis", "report": "report"},
    )
    graph.add_edge("deep_analysis", "report")
    graph.add_edge("report", END)

    return graph.compile()


def _route_after_risk(state: CodeImpactState) -> str:
    risk = state.get("risk_assessment", {})
    related_count = len(state.get("related_files", []))
    if risk.get("risk_level") == "high" and related_count > 3:
        return "deep_analysis"
    return "report"


def _recall_analysis_memory(runtime: CodeImpactRuntime, repo: str, git_diff: GitDiff) -> list[dict]:
    query = " ".join([repo, *[file.path for file in git_diff.files]])
    records = runtime.recall(query=query, memory_type="analysis", limit=10)
    context: list[dict] = []
    for record in records:
        if record.source and record.source != repo:
            continue
        payload = _safe_json_loads(record.content)
        context.append(
            {
                "source": record.source,
                "risk_level": payload.get("risk_level", "unknown") if isinstance(payload, dict) else "unknown",
                "risk_reasoning": payload.get("risk_reasoning", record.content[:240]) if isinstance(payload, dict) else record.content[:240],
            }
        )
        if len(context) >= 3:
            break
    return context


def _safe_json_loads(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _git_diff_from_dict(payload: dict) -> GitDiff:
    files: list[GitFileChange] = []
    for file_data in payload.get("files", []):
        hunks = []
        for hunk_data in file_data.get("hunks", []):
            lines = [
                _dict_to_line(line_data)
                for line_data in hunk_data.get("lines", [])
            ]
            hunks.append(
                GitHunk(
                    header=hunk_data["header"],
                    old_start=hunk_data["old_start"],
                    old_count=hunk_data["old_count"],
                    new_start=hunk_data["new_start"],
                    new_count=hunk_data["new_count"],
                    lines=lines,
                )
            )
        files.append(
            GitFileChange(
                old_path=file_data["old_path"],
                new_path=file_data["new_path"],
                change_type=file_data.get("change_type", "modified"),
                hunks=hunks,
                renamed_from=file_data.get("renamed_from"),
                renamed_to=file_data.get("renamed_to"),
            )
        )
    return GitDiff(files=files)


def _dict_to_line(payload: dict):
    from .diff_parser import DiffLine

    return DiffLine(
        kind=payload["kind"],
        content=payload["content"],
        old_lineno=payload.get("old_lineno"),
        new_lineno=payload.get("new_lineno"),
    )

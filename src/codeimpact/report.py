from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .ast_graph import RelatedFile
from .diff_parser import GitDiff


@dataclass(slots=True)
class ImpactReport:
    repo: str
    generated_at: str
    changed_files: list[str]
    related_files: list[dict]
    risk_level: str
    risk_reasoning: str
    risk_source: str
    test_focus: list[str] = field(default_factory=list)
    review_focus: list[str] = field(default_factory=list)
    confidence: float = 0.0
    assumptions: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    retrieved_context: list[dict] = field(default_factory=list)
    context_sources: list[str] = field(default_factory=list)
    retrieval_ms: float = 0.0
    risks: list[str] = field(default_factory=list)
    test_suggestions: list[str] = field(default_factory=list)
    rollback_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "generated_at": self.generated_at,
            "changed_files": self.changed_files,
            "related_files": self.related_files,
            "risk_level": self.risk_level,
            "risk_reasoning": self.risk_reasoning,
            "risk_source": self.risk_source,
            "test_focus": self.test_focus,
            "review_focus": self.review_focus,
            "confidence": self.confidence,
            "assumptions": self.assumptions,
            "evidence": self.evidence,
            "retrieved_context": self.retrieved_context,
            "context_sources": self.context_sources,
            "retrieval_ms": self.retrieval_ms,
            "risks": self.risks,
            "test_suggestions": self.test_suggestions,
            "rollback_notes": self.rollback_notes,
        }


def build_basic_report(
    repo: str,
    git_diff: GitDiff,
    related: list[RelatedFile],
    risk_assessment: dict | None = None,
    *,
    retrieved_context: list[dict] | None = None,
    context_sources: list[str] | None = None,
    retrieval_ms: float = 0.0,
) -> ImpactReport:
    changed_files = [_normalize_changed_path(file.path) for file in git_diff.files]
    related_payload = [item.to_dict() for item in related]
    risks = [
        "Changed Python files may affect imported downstream modules."
    ] if related else [
        "No reverse dependencies were found by AST analysis."
    ]
    test_suggestions = suggest_tests(repo, git_diff, related)
    rollback_notes = ["Revert the last commit or restore touched files from git if regression is observed."]
    risk_assessment = risk_assessment or {}
    retrieved_context = retrieved_context or []
    return ImpactReport(
        repo=repo,
        generated_at=datetime.now(timezone.utc).isoformat(),
        changed_files=changed_files,
        related_files=related_payload,
        risk_level=str(risk_assessment.get("risk_level", "unknown")),
        risk_reasoning=str(risk_assessment.get("risk_reasoning", "No LLM assessment available; fallback heuristics used.")),
        risk_source=str(risk_assessment.get("risk_source", "fallback")),
        test_focus=_as_string_list(risk_assessment.get("test_focus")),
        review_focus=_as_string_list(risk_assessment.get("review_focus")),
        confidence=_as_confidence(risk_assessment.get("confidence")),
        assumptions=_as_string_list(risk_assessment.get("assumptions")),
        evidence=_as_dict_list(risk_assessment.get("evidence")),
        retrieved_context=_as_dict_list(retrieved_context),
        context_sources=context_sources or _default_context_sources(retrieved_context),
        retrieval_ms=float(retrieval_ms),
        risks=risks,
        test_suggestions=test_suggestions,
        rollback_notes=rollback_notes,
    )


def suggest_tests(repo: str, git_diff: GitDiff, related: list[RelatedFile]) -> list[str]:
    changed_files = [_normalize_changed_path(file.path) for file in git_diff.files]
    related_files = [item.path for item in related]
    suggestions: list[str] = []

    for path in changed_files:
        module_name = Path(path).stem
        suggestions.append(f"Run unit tests covering `{path}`")
        if path.endswith("__init__.py"):
            suggestions.append(f"Run import smoke tests for the package surface in `{path}`")
        else:
            suggestions.append(f"Run regression tests around `{module_name}` consumers")

    if related_files:
        joined = ", ".join(related_files[:5])
        suggestions.append(f"Run downstream regression tests for: {joined}")
    else:
        suggestions.append("No reverse dependencies were found; run the module's own test file and a smoke test.")

    return suggestions


def _normalize_changed_path(path: str) -> str:
    path = path.replace('\\', '/')
    if path.startswith('a/') or path.startswith('b/'):
        return path[2:]
    if path.startswith('/dev/null'):
        return path
    return Path(path).as_posix()


def _as_string_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _as_dict_list(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_confidence(value) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _default_context_sources(retrieved_context: list[dict]) -> list[str]:
    sources = ["AST reverse dependency"]
    if retrieved_context:
        sources.append("RAG retrieved code/test/doc context")
    return sources

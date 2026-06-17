"""Risk assessment helpers for CodeImpact Agent."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .ast_graph import RelatedFile
from .diff_parser import GitDiff


RISK_LEVELS = {"low", "medium", "high"}
_DOTENV_LOADED = False


def call_risk_model(
    repo: str,
    git_diff: GitDiff,
    related: list[RelatedFile],
    memory_context: list[dict] | None = None,
    retrieved_context: list[dict] | None = None,
) -> dict | None:
    _load_dotenv()
    if os.getenv("CODEIMPACT_ENABLE_LLM", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_API_BASE")
    model = os.getenv("OPENAI_CHAT_MODEL", "deepseek-chat")
    if not api_key or not base_url:
        return None

    try:
        from openai import OpenAI
    except Exception:
        return None

    client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"), timeout=float(os.getenv("CODEIMPACT_LLM_TIMEOUT", "20")))
    prompt = _build_risk_prompt(repo, git_diff, related, memory_context=memory_context, retrieved_context=retrieved_context)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You assess code change risk and return JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        assessed = json.loads(content)
    except Exception:
        return None

    normalized = _normalize_risk_assessment(assessed, source="llm")
    if normalized is None:
        return None
    if not normalized["test_focus"]:
        normalized["test_focus"] = _fallback_test_focus(git_diff, related)
    if not normalized["review_focus"]:
        normalized["review_focus"] = _fallback_review_focus(git_diff, related)
    if not normalized["evidence"]:
        normalized["evidence"] = _summarize_diff_hunks(git_diff)
    return normalized


def fallback_risk_assessment(git_diff: GitDiff, related: list[RelatedFile]) -> dict:
    if related:
        return {
            "risk_level": "medium" if len(related) < 3 else "high",
            "risk_reasoning": f"AST found {len(related)} reverse dependencies for the touched module(s); downstream tests should be prioritized.",
            "risk_source": "fallback",
            "test_focus": _fallback_test_focus(git_diff, related),
            "review_focus": _fallback_review_focus(git_diff, related),
            "confidence": 0.62 if len(related) < 3 else 0.72,
            "assumptions": [
                "Risk is inferred from Python import relationships, not runtime coverage data.",
                "Dynamic imports and reflection may be missed by AST analysis.",
            ],
            "evidence": _summarize_diff_hunks(git_diff),
        }
    if git_diff.added or git_diff.deleted:
        return {
            "risk_level": "low",
            "risk_reasoning": "No reverse dependencies were found by AST analysis, but targeted module tests are still recommended.",
            "risk_source": "fallback",
            "test_focus": _fallback_test_focus(git_diff, related),
            "review_focus": _fallback_review_focus(git_diff, related),
            "confidence": 0.55,
            "assumptions": [
                "No reverse imports were detected in parsed Python files.",
                "The change may still affect runtime behavior inside the touched module.",
            ],
            "evidence": _summarize_diff_hunks(git_diff),
        }
    return {
        "risk_level": "unknown",
        "risk_reasoning": "The diff did not contain a material change that affected dependency analysis.",
        "risk_source": "fallback",
        "test_focus": [],
        "review_focus": ["Check whether the supplied diff contains Python file hunks."],
        "confidence": 0.2,
        "assumptions": ["The parser found no added or deleted lines in the supplied diff."],
        "evidence": _summarize_diff_hunks(git_diff),
    }


def _build_risk_prompt(
    repo: str,
    git_diff: GitDiff,
    related: list[RelatedFile],
    memory_context: list[dict] | None = None,
    retrieved_context: list[dict] | None = None,
) -> str:
    changed_files = [file.path for file in git_diff.files]
    related_paths = [item.path for item in related]
    summary = {
        "repo": repo,
        "changed_files": changed_files,
        "related_files": related_paths,
        "added_lines": git_diff.added,
        "deleted_lines": git_diff.deleted,
        "diff_hunk_evidence": _summarize_diff_hunks(git_diff),
        "retrieved_context": retrieved_context or [],
        "historical_analysis": memory_context or [],
    }
    return (
        "You are a senior Python code-review agent. Deterministic tools have already parsed "
        "the git diff and built an AST reverse-import graph. Use that evidence to make the "
        "LLM-only judgment: risk severity, review focus, test focus, confidence, and assumptions.\n\n"
        "Risk rubric:\n"
        "- high: public interface/core module change, deletion, broad reverse dependencies, or migration-like behavior.\n"
        "- medium: meaningful logic change with limited downstream impact or uncertain behavior from historical memory.\n"
        "- low: docs/tests/small localized implementation change with no detected downstream importers.\n\n"
        "Return valid JSON only with this schema:\n"
        "{\n"
        '  "risk_level": "low|medium|high",\n'
        '  "risk_reasoning": "2-4 sentences grounded in changed files, related files, diff evidence, and memory.",\n'
        '  "test_focus": ["specific tests or scenarios to prioritize"],\n'
        '  "review_focus": ["specific code-review questions or files to inspect"],\n'
        '  "confidence": 0.0,\n'
        '  "assumptions": ["important uncertainty or limitation"],\n'
        '  "evidence": [{"path": "file.py", "change_type": "modified", "added": ["..."], "deleted": ["..."]}]\n'
        "}\n\n"
        "Rules:\n"
        "- Do not invent files outside changed_files or related_files.\n"
        "- Keep confidence between 0 and 1.\n"
        "- If AST related_files are empty, explain why the risk can still be non-zero.\n"
        "- Prefer concrete test/review targets over generic advice.\n\n"
        f"{json.dumps(summary, ensure_ascii=False, indent=2)}"
    )


def _normalize_risk_assessment(payload: dict[str, Any], source: str) -> dict | None:
    risk_level = str(payload.get("risk_level", "unknown")).lower()
    risk_reasoning = str(payload.get("risk_reasoning", "")).strip()
    if risk_level not in RISK_LEVELS or not risk_reasoning:
        return None

    return {
        "risk_level": risk_level,
        "risk_reasoning": risk_reasoning,
        "risk_source": source,
        "test_focus": _coerce_string_list(payload.get("test_focus"))[:6],
        "review_focus": _coerce_string_list(payload.get("review_focus"))[:6],
        "confidence": _coerce_confidence(payload.get("confidence")),
        "assumptions": _coerce_string_list(payload.get("assumptions"))[:6],
        "evidence": _coerce_evidence(payload.get("evidence"))[:8],
    }


def _summarize_diff_hunks(git_diff: GitDiff, max_lines_per_file: int = 8) -> list[dict]:
    evidence: list[dict] = []
    for file_change in git_diff.files:
        added: list[str] = []
        deleted: list[str] = []
        for hunk in file_change.hunks:
            for line in hunk.lines:
                if line.kind == "add" and len(added) < max_lines_per_file:
                    added.append(_trim_line(line.content))
                elif line.kind == "delete" and len(deleted) < max_lines_per_file:
                    deleted.append(_trim_line(line.content))
        evidence.append(
            {
                "path": file_change.path,
                "change_type": file_change.change_type,
                "added": added,
                "deleted": deleted,
            }
        )
    return evidence


def _fallback_test_focus(git_diff: GitDiff, related: list[RelatedFile]) -> list[str]:
    focus = [f"Run tests covering `{file.path}`" for file in git_diff.files[:4]]
    if related:
        focus.append("Run downstream tests for modules that import the touched files.")
    return focus


def _fallback_review_focus(git_diff: GitDiff, related: list[RelatedFile]) -> list[str]:
    focus = [f"Inspect behavioral changes in `{file.path}`" for file in git_diff.files[:4]]
    if related:
        focus.append("Check whether changed symbols are part of an imported API used by related files.")
    return focus


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _coerce_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, confidence))


def _coerce_evidence(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    evidence: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            evidence.append(
                {
                    "path": str(item.get("path", "")),
                    "change_type": str(item.get("change_type", "modified")),
                    "added": _coerce_string_list(item.get("added"))[:8],
                    "deleted": _coerce_string_list(item.get("deleted"))[:8],
                }
            )
    return evidence


def _trim_line(text: str, max_len: int = 180) -> str:
    text = text.strip()
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


def _load_dotenv() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True

    for directory in [Path.cwd(), *Path.cwd().parents]:
        env_path = directory / ".env"
        if env_path.exists():
            _read_dotenv(env_path)
            return


def _read_dotenv(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

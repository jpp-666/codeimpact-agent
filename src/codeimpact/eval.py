from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from codeimpact.ast_graph import build_python_dependency_graph
from codeimpact.diff_parser import parse_git_diff
from codeimpact.rag.retriever import CodeContextRetriever, build_context_query
from codeimpact.rag.search import LightweightRetriever
from codeimpact.report import build_basic_report


@dataclass(slots=True)
class EvalRow:
    repo: str
    diff_file: str
    expected_changed: str
    expected_related: str
    expected_context_files: str = ""
    query: str = ""


def load_eval_rows(csv_path: str | Path) -> list[EvalRow]:
    csv_path = Path(csv_path).resolve()
    base_dir = csv_path.parent
    rows: list[EvalRow] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            row = dict(row)
            row["repo"] = _resolve_csv_path(base_dir, row["repo"])
            row["diff_file"] = _resolve_csv_path(base_dir, row["diff_file"])
            rows.append(EvalRow(**row))
    return rows


def run_eval(csv_path: str | Path) -> dict:
    csv_path = Path(csv_path).resolve()
    rows = load_eval_rows(csv_path)
    changed_hits = 0
    related_hits = 0
    retrieval_hits = 0
    context_hits = 0
    context_expected_total = 0
    context_retrieved_total = 0
    context_rr_total = 0.0
    total = 0
    lightweight_cache: dict[str, LightweightRetriever] = {}
    context_cache: dict[str, CodeContextRetriever] = {}

    for row in rows:
        repo = Path(row.repo)
        diff_text = Path(row.diff_file).read_text(encoding="utf-8")
        parsed = parse_git_diff(diff_text)
        graph = build_python_dependency_graph(repo)
        related = graph.related_files([repo / file.path for file in parsed.files])
        build_basic_report(str(repo), parsed, related)
        retriever = lightweight_cache.setdefault(str(repo), LightweightRetriever(repo))
        hits = retriever.search(row.query or row.expected_changed, top_k=5)
        hit_paths = {
            Path(hit.path).resolve().relative_to(repo.resolve()).as_posix()
            for hit in hits
        }
        context_retriever = context_cache.setdefault(str(repo), CodeContextRetriever(repo))
        context_query = build_context_query(repo, parsed, related)
        if row.query:
            context_query = f"{context_query} {row.query}".strip()
        context_result = context_retriever.search(context_query, top_k=5, exclude_paths=[repo / file.path for file in parsed.files])
        context_paths = [
            Path(hit.path).resolve().relative_to(repo.resolve()).as_posix()
            for hit in context_result.hits
        ]
        expected_context_files = _split_expected_files(row.expected_context_files)

        total += 1
        changed_paths = {file.path for file in parsed.files}
        related_paths = {
            Path(item.path).resolve().relative_to(repo.resolve()).as_posix()
            for item in related
        }
        if row.expected_changed in changed_paths:
            changed_hits += 1
        if row.expected_related == "":
            related_hits += 1 if not related_paths else 0
        elif row.expected_related in related_paths:
            related_hits += 1
        if row.expected_related and row.expected_related in hit_paths:
            retrieval_hits += 1
        if expected_context_files:
            context_expected_total += len(expected_context_files)
            context_retrieved_total += len(context_paths)
            matched_positions = [index + 1 for index, path in enumerate(context_paths) if path in expected_context_files]
            context_hits += len(set(expected_context_files) & set(context_paths))
            if matched_positions:
                context_rr_total += 1 / min(matched_positions)

    return {
        "total": total,
        "changed_file_hit_rate": changed_hits / total if total else 0.0,
        "related_file_hit_rate": related_hits / total if total else 0.0,
        "retrieval_hit_rate": retrieval_hits / total if total else 0.0,
        "context_recall_at_5": context_hits / context_expected_total if context_expected_total else 0.0,
        "context_precision_at_5": context_hits / context_retrieved_total if context_retrieved_total else 0.0,
        "context_mrr_at_5": context_rr_total / total if total else 0.0,
    }


def _resolve_csv_path(base_dir: Path, value: str) -> str:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    return str(candidate)


def _split_expected_files(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]

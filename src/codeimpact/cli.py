"""Minimal CLI for CodeImpact Agent."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .ast_graph import build_python_dependency_graph
from .diff_parser import parse_git_diff
from .eval import run_eval
from .graph import CodeImpactRuntime, create_workflow
from .memory.sqlite_memory import SQLiteMemoryStore
from .report import build_basic_report
from .rag.retriever import retrieve_context_for_diff
from .risk import call_risk_model, fallback_risk_assessment

app = typer.Typer(add_completion=False)


@app.command()
def analyze(
    repo: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    diff: Path | None = typer.Option(None, exists=True, file_okay=True, dir_okay=False, resolve_path=True),
    diff_text: str | None = typer.Option(None, help="Raw diff text, used when --diff is not provided."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Print JSON output."),
) -> None:
    if diff is not None:
        text = diff.read_text(encoding="utf-8")
    elif diff_text is not None:
        text = diff_text
    else:
        raise typer.BadParameter("Provide either --diff or --diff-text")

    parsed = parse_git_diff(text)
    graph = build_python_dependency_graph(repo)
    changed_paths = [repo / file.path for file in parsed.files]
    related = graph.related_files(changed_paths)
    retrieved = retrieve_context_for_diff(repo, parsed, related, top_k=5)
    risk_assessment = call_risk_model(
        str(repo),
        parsed,
        related,
        retrieved_context=[hit.to_dict(repo) for hit in retrieved.hits],
    ) or fallback_risk_assessment(parsed, related)
    context_sources = ["AST reverse dependency"]
    if retrieved.hits:
        context_sources.append("RAG retrieved code/test/doc context")
    payload = build_basic_report(
        str(repo),
        parsed,
        related,
        risk_assessment=risk_assessment,
        retrieved_context=[hit.to_dict(repo) for hit in retrieved.hits],
        context_sources=context_sources,
        retrieval_ms=retrieved.retrieval_ms,
    ).to_dict()
    payload["dependency_graph"] = graph.to_dict()
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(payload)


@app.command()
def analyze_graph(
    repo: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    diff: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False, resolve_path=True),
    memory_db: Path = typer.Option(Path("memory.sqlite3"), help="SQLite memory path."),
) -> None:
    runtime = CodeImpactRuntime(memory=SQLiteMemoryStore(memory_db), repo_root=repo)
    app_graph = create_workflow(runtime)
    state = app_graph.invoke({"repo": str(repo), "diff_text": diff.read_text(encoding="utf-8")})
    typer.echo(json.dumps(state.get("report", {}), ensure_ascii=False, indent=2))


@app.command()
def evaluate(
    csv_path: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False, resolve_path=True),
) -> None:
    typer.echo(json.dumps(run_eval(csv_path), ensure_ascii=False, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()

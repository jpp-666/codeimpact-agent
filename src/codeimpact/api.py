"""FastAPI service surface for CodeImpact Agent."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .diff_parser import parse_git_diff
from .graph import CodeImpactRuntime, create_workflow
from .memory.sqlite_memory import SQLiteMemoryStore


app = FastAPI(
    title="CodeImpact Agent API",
    version="0.1.0",
    description="HTTP API for Python code change impact analysis.",
)


class AnalyzeRequest(BaseModel):
    repo: str = Field(..., description="Path to the Python repository to analyze.")
    diff_text: str | None = Field(None, description="Raw git diff text.")
    diff_path: str | None = Field(None, description="Path to a git diff file.")
    memory_db: str = Field("memory.sqlite3", description="SQLite memory database path.")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/changed-files")
def changed_files(payload: AnalyzeRequest) -> dict:
    diff_text = _load_diff_text(payload)
    parsed = parse_git_diff(diff_text)
    return {"changed_files": [file.path for file in parsed.files]}


@app.post("/analyze")
def analyze(payload: AnalyzeRequest) -> dict:
    repo = Path(payload.repo).expanduser().resolve()
    if not repo.is_dir():
        raise HTTPException(status_code=400, detail=f"Repository does not exist: {repo}")

    diff_text = _load_diff_text(payload)
    memory_db = Path(payload.memory_db).expanduser()
    runtime = CodeImpactRuntime(memory=SQLiteMemoryStore(memory_db), repo_root=repo)
    workflow = create_workflow(runtime)
    state = workflow.invoke({"repo": str(repo), "diff_text": diff_text})
    return state.get("report", {})


def _load_diff_text(payload: AnalyzeRequest) -> str:
    if payload.diff_text:
        return payload.diff_text
    if payload.diff_path:
        diff_path = Path(payload.diff_path).expanduser().resolve()
        if not diff_path.is_file():
            raise HTTPException(status_code=400, detail=f"Diff file does not exist: {diff_path}")
        return diff_path.read_text(encoding="utf-8")
    raise HTTPException(status_code=400, detail="Provide either diff_text or diff_path.")

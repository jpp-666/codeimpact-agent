import json
from pathlib import Path

from codeimpact.graph import CodeImpactRuntime, create_workflow
from codeimpact.memory.sqlite_memory import SQLiteMemoryStore


def test_graph_recalls_analysis_memory(tmp_path: Path) -> None:
    repo = _make_repo_with_importers(tmp_path, importer_count=1)
    memory = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    memory.store(
        "codeimpact",
        json.dumps({"risk_level": "high", "risk_reasoning": "Previous router change broke downstream tests."}),
        memory_type="analysis",
        source=str(repo),
    )
    workflow = create_workflow(CodeImpactRuntime(memory=memory))

    state = workflow.invoke({"repo": str(repo), "diff_text": _diff_for("pkg/core.py")})
    report = state["report"]

    assert report["memory_context"]
    assert report["memory_context"][0]["risk_level"] == "high"
    assert "retrieved_context" in report
    assert "retrieval_ms" in report


def test_graph_routes_high_risk_to_deep_analysis(tmp_path: Path) -> None:
    repo = _make_repo_with_importers(tmp_path, importer_count=4)
    workflow = create_workflow(CodeImpactRuntime(memory=SQLiteMemoryStore(tmp_path / "memory.sqlite3")))

    state = workflow.invoke({"repo": str(repo), "diff_text": _diff_for("pkg/core.py")})
    report = state["report"]

    assert report["risk_level"] == "high"
    assert report["deep_analysis"]["trigger"] == "high risk with broad reverse dependencies"
    assert report["deep_analysis"]["recommendations"]


def _make_repo_with_importers(tmp_path: Path, importer_count: int) -> Path:
    repo = tmp_path / "repo"
    package = repo / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text("def service():\n    return 1\n", encoding="utf-8")
    for index in range(importer_count):
        (repo / f"consumer_{index}.py").write_text("from pkg.core import service\n", encoding="utf-8")
    return repo


def _diff_for(path: str) -> str:
    return "\n".join(
        [
            f"diff --git a/{path} b/{path}",
            f"--- a/{path}",
            f"+++ b/{path}",
            "@@ -1,2 +1,2 @@",
            " def service():",
            "-    return 1",
            "+    return 2",
        ]
    )

from pathlib import Path

from fastapi.testclient import TestClient

from codeimpact.api import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_changed_files_endpoint() -> None:
    response = client.post(
        "/changed-files",
        json={"repo": ".", "diff_text": _diff_for("pkg/core.py")},
    )

    assert response.status_code == 200
    assert response.json() == {"changed_files": ["pkg/core.py"]}


def test_analyze_endpoint_runs_workflow(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    response = client.post(
        "/analyze",
        json={
            "repo": str(repo),
            "diff_text": _diff_for("pkg/core.py"),
            "memory_db": str(tmp_path / "memory.sqlite3"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["changed_files"] == ["pkg/core.py"]
    assert payload["risk_source"] == "fallback"
    assert payload["related_files"]
    assert isinstance(payload["retrieved_context"], list)


def test_analyze_endpoint_requires_diff() -> None:
    response = client.post("/analyze", json={"repo": "."})

    assert response.status_code == 400
    assert "Provide either diff_text or diff_path" in response.json()["detail"]


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    package = repo / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text("def service():\n    return 1\n", encoding="utf-8")
    (repo / "consumer.py").write_text("from pkg.core import service\n", encoding="utf-8")
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

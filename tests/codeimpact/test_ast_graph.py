from pathlib import Path

from codeimpact.ast_graph import build_python_dependency_graph


def test_dependency_graph_tracks_import_alias_and_reexport(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "pkg").mkdir()
    (repo / "pkg" / "__init__.py").write_text("from .core import service\n", encoding="utf-8")
    (repo / "pkg" / "core.py").write_text(
        "import pkg.helpers as helpers\n"
        "def service():\n"
        "    return helpers.answer()\n",
        encoding="utf-8",
    )
    (repo / "pkg" / "helpers.py").write_text(
        "def answer():\n"
        "    return 42\n",
        encoding="utf-8",
    )
    (repo / "consumer.py").write_text(
        "from pkg import service\n"
        "import importlib\n"
        "core = importlib.import_module('pkg.core')\n"
        "print(core.service())\n",
        encoding="utf-8",
    )

    graph = build_python_dependency_graph(repo)
    related = graph.related_files([repo / "pkg" / "core.py"], max_depth=3)
    related_paths = {Path(item.path).relative_to(repo).as_posix() for item in related}

    assert "pkg/__init__.py" in related_paths
    assert "consumer.py" in related_paths


def test_dependency_graph_handles_relative_imports(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text("from .helpers import util\n", encoding="utf-8")
    (repo / "helpers.py").write_text("def util():\n    return 1\n", encoding="utf-8")
    (repo / "wrapper.py").write_text("from service import util\n", encoding="utf-8")

    graph = build_python_dependency_graph(repo)
    related = graph.related_files([repo / "helpers.py"], max_depth=2)
    related_paths = {Path(item.path).relative_to(repo).as_posix() for item in related}

    assert "service.py" in related_paths
    assert "wrapper.py" in related_paths

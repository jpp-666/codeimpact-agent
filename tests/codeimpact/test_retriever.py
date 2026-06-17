from codeimpact.rag.search import LightweightRetriever


def test_lightweight_retriever_finds_markdown(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("LangGraph orchestrates agent workflows", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("SQLite memory stores historical context", encoding="utf-8")

    retriever = LightweightRetriever(tmp_path)
    hits = retriever.search("agent workflows", top_k=2)

    assert hits
    assert hits[0].path.endswith("guide.md")


def test_lightweight_retriever_returns_empty_for_missing_query(tmp_path):
    (tmp_path / "a.md").write_text("nothing useful here", encoding="utf-8")

    retriever = LightweightRetriever(tmp_path)
    hits = retriever.search("unrelated term", top_k=2)

    assert hits == []

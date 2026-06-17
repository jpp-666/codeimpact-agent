from codeimpact.memory.sqlite_memory import SQLiteMemoryStore


def test_sqlite_memory_store_and_recall(tmp_path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")

    store.store("agent", "User wants Python-only analysis", memory_type="goal")
    store.store("agent", "Use AST first, rg as fallback", memory_type="policy")

    recalled = store.recall("agent", query="AST fallback", limit=2)

    assert len(recalled) == 2
    assert recalled[0].memory_type == "policy"
    assert "AST" in recalled[0].content


def test_sqlite_memory_consolidate_removes_duplicates(tmp_path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")

    store.store("agent", "duplicate memory", memory_type="note")
    store.store("agent", "duplicate memory", memory_type="note")
    store.store("agent", "unique memory", memory_type="note")

    removed = store.consolidate("agent", memory_type="note")

    assert removed == 1
    assert len(store.recall("agent", memory_type="note", limit=10)) == 2

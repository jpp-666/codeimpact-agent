from codeimpact.rag.adapters import create_retriever
from codeimpact.memory.adapters import create_memory_store


def test_backend_factories_return_local_implementations(tmp_path):
    retriever = create_retriever(tmp_path)
    memory = create_memory_store(tmp_path / 'memory.sqlite3')

    assert hasattr(retriever, 'search')
    assert hasattr(memory, 'store')
    assert hasattr(memory, 'recall')

from pathlib import Path
import asyncio

import codeimpact.mcp_server as mcp_server
from codeimpact.mcp_server import mcp


def test_mcp_lists_expected_tools() -> None:
    tools = asyncio.run(mcp.list_tools())
    names = [tool.name for tool in tools]

    assert 'get_changed_files' in names
    assert 'analyze_diff' in names
    assert 'search_code_context' in names
    assert 'suggest_tests' in names
    assert 'save_memory' in names
    assert 'recall_memory' in names


def test_mcp_call_tool_get_changed_files() -> None:
    diff_text = '\n'.join(
        [
            'diff --git a/a.py b/a.py',
            '--- a/a.py',
            '+++ b/a.py',
            '@@ -1 +1 @@',
            '-x = 1',
            '+x = 2',
        ]
    )
    result = asyncio.run(mcp.call_tool('get_changed_files', {'diff_text': diff_text}))
    payload = result.structured_content
    if isinstance(payload, dict) and 'result' in payload:
        payload = payload['result']
    assert payload == ['a.py']


def test_mcp_call_tool_suggest_tests() -> None:
    repo = Path('data/eval/sample_repo').resolve()
    diff_text = Path('data/eval/sample_core.diff').read_text(encoding='utf-8')
    result = asyncio.run(
        mcp.call_tool(
            'suggest_tests',
            {'repo': str(repo), 'diff_text': diff_text},
        )
    )

    payload = result.structured_content
    assert payload['suggestions']
    assert payload['changed_files'] == ['pkg/core.py']


def test_analyze_diff_uses_langgraph_workflow(monkeypatch) -> None:
    calls = {}

    class FakeWorkflow:
        def invoke(self, state):
            calls['state'] = state
            return {
                'report': {
                    'changed_files': ['pkg/core.py'],
                    'risk_level': 'low',
                    'risk_source': 'fallback',
                    'memory_context': [{'risk_level': 'medium'}],
                }
            }

    def fake_create_workflow(runtime):
        calls['runtime'] = runtime
        return FakeWorkflow()

    monkeypatch.setattr(mcp_server, 'create_workflow', fake_create_workflow)

    report = mcp_server.analyze_diff('repo-path', 'diff-text')

    assert calls['state'] == {'repo': 'repo-path', 'diff_text': 'diff-text'}
    assert calls['runtime'].repo_root == Path('repo-path')
    assert report['risk_source'] == 'fallback'
    assert report['memory_context']

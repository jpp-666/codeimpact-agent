from pathlib import Path

from typer.testing import CliRunner

from codeimpact.cli import app


runner = CliRunner()


def test_cli_analyze_outputs_json(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'a.py').write_text("print('hi')\n", encoding='utf-8')
    diff = tmp_path / 'diff.txt'
    diff.write_text(
        '\n'.join(
            [
                'diff --git a/a.py b/a.py',
                '--- a/a.py',
                '+++ b/a.py',
                '@@ -1 +1 @@',
                "-print('hi')",
                "+print('bye')",
            ]
        ),
        encoding='utf-8',
    )

    result = runner.invoke(app, ['analyze', '--repo', str(repo), '--diff', str(diff)])

    assert result.exit_code == 0
    assert '"changed_files"' in result.stdout
    assert '"related_files"' in result.stdout
    assert '"risk_level"' in result.stdout
    assert '"test_focus"' in result.stdout
    assert '"review_focus"' in result.stdout
    assert '"confidence"' in result.stdout
    assert '"retrieved_context"' in result.stdout
    assert '"context_sources"' in result.stdout

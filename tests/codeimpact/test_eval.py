from pathlib import Path

from codeimpact.eval import run_eval


def test_eval_runner_reports_hits():
    sample_csv = Path(__file__).parents[2] / 'data' / 'eval' / 'sample.csv'
    result = run_eval(sample_csv)

    assert result['total'] >= 5
    assert result['changed_file_hit_rate'] == 1.0
    assert 0 < result['related_file_hit_rate'] < 1.0
    assert 0 < result['retrieval_hit_rate'] <= 1.0
    assert 0 <= result['context_recall_at_5'] <= 1.0
    assert 0 <= result['context_precision_at_5'] <= 1.0
    assert 0 <= result['context_mrr_at_5'] <= 1.0

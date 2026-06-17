from pkg.service import summarize


def test_summarize_includes_run():
    assert summarize()["run"] == 2

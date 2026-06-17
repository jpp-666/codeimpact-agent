from pkg.core import run


def test_run_returns_expected_value():
    assert run() == 2

from pkg.util import helper


def test_helper_returns_primitive_value():
    assert helper() == 1

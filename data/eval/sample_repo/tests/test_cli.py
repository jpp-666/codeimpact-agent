from cli import command


def test_command_returns_run_value():
    assert command() == 2

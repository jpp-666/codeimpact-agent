from app import main


def test_main_uses_package_run():
    assert main() == 2

import importlib

service = importlib.import_module("pkg.service")


def load_summary():
    return service.summarize()

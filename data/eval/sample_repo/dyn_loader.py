import importlib

target = "pkg.core"
core = importlib.import_module(target)

def load():
    return core.run()

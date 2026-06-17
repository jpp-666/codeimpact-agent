# Sample Repo

This repo demonstrates a tiny Python package for CodeImpact evaluation.

- `pkg.core.run()` returns a value based on `pkg.util.helper()`
- `pkg.util.helper()` is the low-level primitive used by the package
- `app.main()` calls `pkg.run()` from the package export surface

The main test coverage lives in `tests/test_core.py` and `tests/test_app.py`.

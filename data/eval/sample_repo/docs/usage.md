# Usage

The package exports `run` from `pkg.__init__`.

`app.main()` depends on the package export and is a good regression target when core behavior changes.

For code changes in `pkg.core`, run the package tests and the app-level smoke test together.

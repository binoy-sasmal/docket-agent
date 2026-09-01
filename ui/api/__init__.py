"""HTTP layer for the Docket approval and eval views.

This package lives outside `src/` deliberately. `docket` is the system under
test; this is a viewer onto it. Keeping the two apart means:

- `pyproject.toml`'s `[tool.mypy] files = ["src", "tools"]` strict gate and the
  `[tool.setuptools.packages.find] where = ["src"]` package boundary keep
  covering exactly what they covered before the UI existed, and CI does not
  need FastAPI installed to run them.
- Nothing here can be imported by `docket`, so no UI concern can leak into the
  architecture invariants in tests/test_architecture.py.

Everything in here is read-and-display plus the one human action the graph
already exposes: resuming its approval `interrupt()`. There is no endpoint
that posts anything to anything, because `docket` has no such capability
(docs/PROJECT.md section 3.1).
"""

# Docket

> An ERP invoice exception agent that investigates, cites its evidence, and
> proposes -- but cannot post.

This does not solve accounts-payable exception handling. Organisations buy that
from vendors with implementation teams. This is a portfolio system demonstrating
agent architecture, grounding discipline, and measurable guardrails against a
realistic ERP process.

Full project description: [docs/PROJECT.md](docs/PROJECT.md).

## Status

Session 1 (BPIC 2019 derivation) is code-complete and awaiting the human
hand-check gate. ~300 line items are rendered to `fixtures/rendered/`; the
case selection is not yet frozen (`fixtures/frozen/` is empty) -- see
[docs/handcheck/](docs/handcheck/) for the three reports that need review
before `python -m docket.freeze` can run. No agent code exists yet.

Full derivation record -- reconnaissance findings, exclusions, the schema,
and every modelling assumption -- is in
[docs/DERIVATION.md](docs/DERIVATION.md).

## Provenance

Derived from the BPI Challenge 2019 event log (van Dongen, B.F., 2019),
4TU.ResearchData, DOI 10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1, licensed
CC BY 4.0. Structural properties are derived from the log; all monetary values,
quantities, dispositions and free-text notes are authored for this project.

See [fixtures/frozen/FROZEN.md](fixtures/frozen/FROZEN.md) for the full
provenance chain once the fixture is frozen.

## Development

```
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.lock.txt
ruff check .
mypy
pytest -m "not slow"
pytest -m slow   # full-log checks, ~500MB CSV, ~40s
```

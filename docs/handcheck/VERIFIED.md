# Hand-check verification

Reviewer: Binoy Sasmal
Date: 2026-09-01

The three hand-check reports in this directory were reviewed against the raw
event rows and found acceptable for the Session 1 freeze gate:

- `4507000477_00060`
- `4507075965_00050`
- `4508063534_00001`

Notes:

- `4508063534_00001` has non-constant raw `event Cumulative net worth (EUR)`
  values on later goods-receipt and invoice rows. This is documented in the
  hand-check report and in `docs/DERIVATION.md`; using the first event's value
  as the case total is accepted for this fixture.
- This file records human sign-off for the hand-check gate. It does not make
  `fixtures/frozen/` or `evals/golden/` editable after freeze.

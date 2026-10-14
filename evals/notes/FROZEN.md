# Frozen eval record: note hypotheses

This directory is Tier 1, like `evals/golden/` (docs/PROJECT.md section 6.1,
AGENTS.md): immutable once written. Nothing here is edited to make an
implementation test pass. A genuine correction requires an explicit new
freeze act recorded below, not a silent label change.

## What it measures

A feature that did not exist when these labels were written: the Investigator
extracting at most one grounded, explicitly UNVERIFIED hypothesis from
untrusted note text, which deterministic code then checks against the
documents. The design, the four hypothesis kinds, the status rules and the
metrics are in `note_hypotheses.json` itself, so the measuring stick and its
definition cannot drift apart.

The decision must never move: every case's disposition, reason code and
policy decision must equal its frozen label in `evals/golden/day3_labels.json`.

## Freeze act 1 -- public cases (2026-10-14)

Promoted from `evals/draft/note_hypotheses_draft.json`
(sha256 `d6cc8aa35e9588448b3a1e6825ddabc1b1d760c335628b3387e32f30cde3c45b`).
The only change on promotion is the `status` field.

- Public cases: 13 (10 with a claim, 3 without)
- Held-out slots: 4, unauthored (`payload_status:
  "to_be_authored_repo_blind_before_final_run"`)

**Review.** Checked by `tools/validate_note_drafts.py`, which reads only the
draft, the golden labels and the rendered fixtures, never implementation
code: every case exists and has a golden label, every note has a document to
attach to, every expected status follows from the written status rules
applied to the raw documents, and every must-not-reach-approver phrase occurs
in its payload. Approved for freezing by the maintainer on 2026-10-14 after
reading the cases and their labels.

**Ordering.** Frozen before any note-hypothesis implementation existed; the
git history shows the labels landing first. Current implementation output was
not used as ground truth, because there was none.

**Authorship, stated plainly.** The public payloads and labels were written by
the same repo-aware session that designed the feature. They are therefore not
independent of it, and a high public score means less than it would
otherwise. The held-out slots exist to address exactly this.

**One amendment before freezing.** The draft first said no note text ever
reaches the approver. The web UI deliberately shows raw notes in a panel
labelled untrusted, so the claim was narrowed before freezing: nothing the
agent *generates* for the approver (proposal summary, claims, hypothesis line)
contains note text. The leakage metric is defined on that output.

## Holdout policy

The four held-out slots get their case, payload and label in a separate
session with no repository access, before any held-out number exists. That
session's text is copied in verbatim by a recorded freeze act 2, which also
re-issues `MANIFEST.sha256`. Public and held-out results are reported
separately and never pooled.

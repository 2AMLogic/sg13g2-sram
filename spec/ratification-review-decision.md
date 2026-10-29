# Decision: post-hoc two-key ratification review of `spec/sram.md`

**Status**: Open. Keys installed; neither key has been run. No verdict is recorded here.
**Issue**: #37 (operator ruling 2026-10-27)
**Text under review**: `spec/sram.md` as merged in #7, commit `2597199`.
**Precedent**: `sg13g2-bandgap` `spec/decision-records/0008-two-key-ratification-review-outcome.md`, a post-hoc two-key review of merged PR #220.

## Decision

Run the two-key review on the text already merged in #7 rather than author a
fresh ratification PR, which the keys would then review with the same
identity that wrote it. `spec/sram.md` stays "Proposed" until the operator
ratifies or rejects on this record.

## What is in place

- `ratification/ee-key/` and `ratification/market-key/`, adapted from
  `2AMLogic/gf180-gate-driver`'s, with an SRAM-macro section in the EE rubric
  and `comps/sram.md` in place of the gate-driver comp data.

## What is not done, and why

Per `2AMLogic/2am` `ratification/protocol.md` §3-§4, `release` refuses a key
whose forge-authenticated poster is in the author set, and requires two
distinct non-author holders. The fleet identity that landed #7 and that built
this installation is in the author set, so it cannot post either marker
without self-review. No `RATIFY-KEY` marker has been posted and none is
fabricated here.

## Open questions for the operator

1. **Reviewer identities.** Both keys need a non-author identity, distinct
   from each other (`2am-ee-key`, `2am-market-key` Apps per protocol.md §1,
   2am#550). Not checked against this repo's actor setup.
2. **Marker target.** `block=<repo>#<PR-or-issue>` must name merged PR
   `2AMLogic/sg13g2-sram#7` or issue #37. protocol.md §3-§4 was read for the
   release rule, not for whether `release` accepts a merged PR or an issue.
3. **Whether `spec/sram.md` changed since `2597199`.** Check before the
   keys run; review the merged text and note any drift. Drift exists:
   `spec/sram-text-consistency-decision.md` (#72) edits the text; re-run the
   check against the new commit.

## Outcome

| Key | Verdict | Marker |
|---|---|---|
| EE | not run | none |
| Market | not run | none |

When the keys have run, replace this table with each key's verdict and a link
to its posted review, list the findings, and state the reviewed commit. If a
key requests changes, the spec stays "Proposed" and each finding is filed as
an issue.

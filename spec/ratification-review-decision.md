# Decision: post-hoc two-key ratification review of `spec/sram.md`

**Status**: Keys run 2026-10-29. Both request changes; `spec/sram.md` stays Proposed. Awaiting operator disposition.
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

## How the keys ran

Operator ruling 2026-10-29 (recorded on #37): no new identities. Each key ran
as agent work in a fresh session that did not write the spec, PR or design,
and posted an ordinary comment on #37 naming its run id. The poster login is
the fleet's single App login, so the forge-authenticated identity is not
distinct from the author set; the session separation is the non-author gate
under that ruling. Both run ids were self-assigned by the sessions (the
harness gave none). The EE key ran first; the market key ran separately and
did not read the EE comment.

## Outcome

Reviewed text: `spec/sram.md` at `2597199` (#7), unchanged since.

| Key | Verdict | Run id | Comment |
|---|---|---|---|
| EE | request-changes (rows 6 and 9 `insufficient-evidence`, none `unsound`) | `ee-key-fresh-session-sonnet-5-5-20261029-r1` | [#37 comment](https://github.com/2AMLogic/sg13g2-sram/issues/37#issuecomment-6510258614) |
| Market | uncompetitive (access time has no target; area and min clock pulse rows absent) | `market-key-issue37-20261029-selfassigned` | [#37 comment](https://github.com/2AMLogic/sg13g2-sram/issues/37#issuecomment-6510277626) |

The market key's `uncompetitive` is its roll-up of the worst in-scope row; it
is not a `request-changes` token, so the operator should read it as blocking
until the access-time row is settled.

## Findings

Each is filed as its own issue:

- #68 margins row has no Monte Carlo evidence (EE F1)
- #69 1 ns write-pulse window unconfirmed (EE F2)
- #70 no wire-RC check or physical organization (EE F3)
- #71 write-margin definition under-specified (EE F4)
- #72 spec text inconsistencies, incl. 27 vs 25 C (EE F5, F6)
- #73 no access-time target (market F1)
- #74 no area, min clock pulse, power or retention rows (market F2, F3)
- #75 Verilog/CDL only stretch; Liberty corner count unspecified (market F4, F5)
- #76 comp data unverified against primary Liberty/LEF (market F7)

Market F6 (no bit mask or BIST) is a catalog gap the spec names itself and is
not filed.

## For the operator

The spec stays "Proposed". Reject, or hold until #68, #69 and #73 are
resolved by decision record; the operator flips the status line, not an agent.
#3 T1 items 5-8 stay unreleased.

# Work Plan

Snapshot of GitHub label state as of the last merged Guide docs-maintenance
PR — it may lag live labels until the next docs-maintenance PR merges and
refreshes this file. Date the snapshot with `git log -1 -- WORK_PLAN.md`.
Only the region between the markers is machine-generated.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#189**: chore(loom): resync installed Loom to v0.19.1302

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#107**: layout: route global control fan-out and per-slice DL/DOUT

## Important

`loom:important`; taken before unlabelled work.

- **#30**: T1 item 4 (LVS clean): klt lvs of the full macro vs the item-1 netlist
- **#31**: T1 item 11 (power delivery): klt erc supply spec for the macro rails
- **#68**: spec: margins row has no Monte Carlo evidence
- **#88**: Macro layout: route periphery, array-to-column-path and pins so the macro is extractable
- **#95**: layout: macro periphery signal nets and pin connection
- **#108**: layout: connect macro pins, signals record, verify and README
- **#152**: Guide docs PRs that edit README.md always drift the item-10 attestation envelope
- **#159**: layout: join the column_mux BLBM net, the one undrawn leaf-cell net

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#107**: layout: route global control fan-out and per-slice DL/DOUT
- **#159**: layout: join the column_mux BLBM net, the one undrawn leaf-cell net

## In Progress

Issues currently being built (`loom:building`).

- **#37**: Post-hoc two-key ratification review of spec/sram.md as merged in #7
- **#56**: Consolidate duplicated helpers across sim/*_post.py into one shared module
- **#69**: spec: confirm the 1 ns write-pulse window
- **#71**: spec: write-margin definition under-specified
- **#72**: spec: internal inconsistencies in sram.md text
- **#74**: spec: no area target, min-clock-pulse, power or retention rows
- **#126**: netlist: scalar WEN vs the origin's per-bit WEN[31:0]; Views row ratified by #79 assumes the per-bit interface
- **#172**: Bump CI's KLT_VERSION pin from 0.8.0 to 0.9.2 so attestation envelopes can be regenerated without a fleet submit

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#77**: docs(spec): record two-key review outcome for sram.md
- **#78**: docs: make spec/sram.md internally consistent on corners, signoff, open items, typical point
- **#80**: docs: add decision record for area, min-clock-pulse, power and retention spec rows
- **#81**: docs(spec): pin the write-margin definition in a decision record

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#189**: chore(loom): resync installed Loom to v0.19.1302

## Proposed

Issues carrying `loom:curated`.

- **#30**: T1 item 4 (LVS clean): klt lvs of the full macro vs the item-1 netlist *(curated)*
- **#37**: Post-hoc two-key ratification review of spec/sram.md as merged in #7 *(curated)*
- **#68**: spec: margins row has no Monte Carlo evidence *(curated)*
- **#69**: spec: confirm the 1 ns write-pulse window *(curated)*
- **#71**: spec: write-margin definition under-specified *(curated)*
- **#72**: spec: internal inconsistencies in sram.md text *(curated)*
- **#74**: spec: no area target, min-clock-pulse, power or retention rows *(curated)*
- **#88**: Macro layout: route periphery, array-to-column-path and pins so the macro is extractable *(curated)*
- **#107**: layout: route global control fan-out and per-slice DL/DOUT *(curated)*
- **#126**: netlist: scalar WEN vs the origin's per-bit WEN[31:0]; Views row ratified by #79 assumes the per-bit interface *(curated)*
- **#159**: layout: join the column_mux BLBM net, the one undrawn leaf-cell net *(curated)*
- **#172**: Bump CI's KLT_VERSION pin from 0.8.0 to 0.9.2 so attestation envelopes can be regenerated without a fleet submit *(curated)*

## Proposed (Architect / Hermit)

- **#56**: Consolidate duplicated helpers across sim/*_post.py into one shared module *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 1 |
| Important | 8 |
| Ready (`loom:issue`) | 2 |
| In Progress (`loom:building`) | 8 |
| PRs awaiting review | 4 |
| Approved PRs awaiting merge | 1 |
| Curated | 12 |
| Architect / Hermit proposals | 1 |
| Active epics | 0 |
<!-- guide:plan-body:end -->

# Work Plan

Snapshot of GitHub label state as of the last merged Guide docs-maintenance
PR — it may lag live labels until the next docs-maintenance PR merges and
refreshes this file. Date the snapshot with `git log -1 -- WORK_PLAN.md`.
Only the region between the markers is machine-generated.

<!-- guide:plan-body:start -->
_Generated: 2026-11-22T07:24:13Z (snapshot; compare against live labels)_
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#107**: layout: route global control fan-out and per-slice DL/DOUT *(held)*

## Important

`loom:important`; taken before unlabelled work.

- **#30**: T1 item 4 (LVS clean): klt lvs of the full macro vs the item-1 netlist *(held)*
- **#31**: T1 item 11 (power delivery): klt erc supply spec for the macro rails *(held)*
- **#68**: spec: margins row has no Monte Carlo evidence *(held)*
- **#88**: Macro layout: route periphery, array-to-column-path and pins so the macro is extractable
- **#95**: layout: macro periphery signal nets and pin connection *(held)*
- **#108**: layout: connect macro pins, signals record, verify and README *(held)*
- **#230**: T1 item 6, pilot: size the write-margin Monte Carlo cost at small n and move the level search onto klt's built-in bisection (feeds the #68 budget decision) *(held)*

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

- **#56**: Consolidate duplicated helpers across sim/*_post.py into one shared module
- **#74**: spec: no area target, min-clock-pulse, power or retention rows

## In Progress

Issues currently being built (`loom:building`).

- **#37**: Post-hoc two-key ratification review of spec/sram.md as merged in #7
- **#69**: spec: confirm the 1 ns write-pulse window
- **#71**: spec: write-margin definition under-specified
- **#72**: spec: internal inconsistencies in sram.md text
- **#126**: netlist: scalar WEN vs the origin's per-bit WEN[31:0]; Views row ratified by #79 assumes the per-bit interface
- **#208**: Re-vendor build-osdi.sh at the new owner hash and read pins from --print-pins
- **#228**: T1 item 7, first increment: klt pex on the LVS-matched 6T bitcell (schematic-vs-extracted read SNM, hold SNM and write margin)
- **#229**: T1 item 11, pre-work: commit the klt erc supply spec, as-built ERC report and negative controls for the macro (split from #31)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#77**: docs(spec): record two-key review outcome for sram.md *(held)*
- **#78**: docs: make spec/sram.md internally consistent on corners, signoff, open items, typical point *(held)*
- **#80**: docs: add decision record for area, min-clock-pulse, power and retention spec rows *(held)*
- **#81**: docs(spec): pin the write-margin definition in a decision record *(held)*

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#30**: T1 item 4 (LVS clean): klt lvs of the full macro vs the item-1 netlist *(curated)* *(held)*
- **#37**: Post-hoc two-key ratification review of spec/sram.md as merged in #7 *(curated)*
- **#68**: spec: margins row has no Monte Carlo evidence *(curated)* *(held)*
- **#69**: spec: confirm the 1 ns write-pulse window *(curated)*
- **#71**: spec: write-margin definition under-specified *(curated)*
- **#72**: spec: internal inconsistencies in sram.md text *(curated)*
- **#74**: spec: no area target, min-clock-pulse, power or retention rows *(curated)*
- **#88**: Macro layout: route periphery, array-to-column-path and pins so the macro is extractable *(curated)*
- **#107**: layout: route global control fan-out and per-slice DL/DOUT *(curated)* *(held)*
- **#126**: netlist: scalar WEN vs the origin's per-bit WEN[31:0]; Views row ratified by #79 assumes the per-bit interface *(curated)*
- **#208**: Re-vendor build-osdi.sh at the new owner hash and read pins from --print-pins *(curated)*
- **#228**: T1 item 7, first increment: klt pex on the LVS-matched 6T bitcell (schematic-vs-extracted read SNM, hold SNM and write margin) *(curated)*
- **#229**: T1 item 11, pre-work: commit the klt erc supply spec, as-built ERC report and negative controls for the macro (split from #31) *(curated)*
- **#230**: T1 item 6, pilot: size the write-margin Monte Carlo cost at small n and move the level search onto klt's built-in bisection (feeds the #68 budget decision) *(curated)* *(held)*

## Proposed (Architect / Hermit)

- **#56**: Consolidate duplicated helpers across sim/*_post.py into one shared module *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 1 |
| Important | 7 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 2 |
| In Progress (`loom:building`) | 8 |
| PRs awaiting review | 4 |
| Approved PRs awaiting merge | 0 |
| Curated | 14 |
| Architect / Hermit proposals | 1 |
| Active epics | 0 |
<!-- guide:plan-body:end -->

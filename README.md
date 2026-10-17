# sg13g2-sram

An SRAM macro on [IHP SG13G2](https://github.com/IHP-GmbH/IHP-Open-PDK), a
130 nm SiGe BiCMOS open PDK — built and verified by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source xschem + ngspice flow.

**Status: just opened, specification phase.** Nothing is designed yet.

**Built agent-native.** Every specification, decision record, testbench, and
line of documentation here is produced by AI agents working from a ratified
spec and an append-only evidence trail — not human-authored work that agents
merely assisted with. Verification is the product: every claim traces to a
recorded result under PVT corners. Where the agents hit friction with the
open-source tooling — most often
[klayout-tools](https://github.com/2AMLogic/klayout-tools) — that friction is
filed as a public issue against the tool itself, so the fix benefits everyone
using SG13G2, not just this repo.

## Why this block, on this PDK

This is a **port, not a new design**. It follows
[gf180-sram](https://github.com/2AMLogic/gf180-sram), which ratified a fixed
1 kB (256 × 32) single-port macro on a custom-drawn 6T bitcell, carried it
through DRC, LVS and 27-corner PVT margin signoff, and generated its own LEF
abstract. That repo is master for the spec structure, the margin
definitions, the statistical treatment and the harness. The experimental
design is the one every fleet port uses: **the PDK is the variable, not the
design.** Anything that breaks here should be assumed to be the PDK, the
deck or the tools before it is assumed to be the macro.

What changes is the PDK underneath:

- **Supply.** SG13G2's core devices run at 1.2 V, against `gf180-sram`'s
  3.3 V. Margins, corners and timing are re-derived for that rail.
- **A foundry reference at the same size.** SG13G2 ships its own SRAM macro
  library (`sg13g2_sram`), single- and dual-port, including a 1-port
  256 × 32 instance — the same organization as the origin's target. It is
  the comparison point for area and timing here, not something this repo
  wraps.
- **The bitcell question reopens.** The origin found gf180mcu's bitcell only
  embedded inside fixed foundry macros and drew its own. Whether SG13G2's
  is usable standalone is the first question, answered before the spec.
- **The deck.** klt's SG13G2 DRC/LVS deck is newer than its gf180mcu one;
  a dense memory array is a new kind of workload for it.

Free SRAM generators exist for other open PDKs; where one is a useful
reference, use it and say so. Do not reimplement it.

## Target specification

The target specification is proposed in [`spec/sram.md`](spec/sram.md), with
the porting plan ([`spec/porting-plan.md`](spec/porting-plan.md)) and the
decision records beside it. It is **not yet ratified**; ratification is an
operator step. Summary of the proposal: fixed 256 × 32 (1 kB) 1RW instance
on a custom-drawn 6T bitcell, 1.2 V ±10%, a 45-corner PVT matrix, and
read SNM, hold SNM and write margin strictly positive at every corner with
Monte Carlo evidence.

Maturity ladder: bitcell question answered → porting plan recorded → spec
ratified → bitcell characterized → array assembled → DRC/LVS-clean →
abstract and Liberty views generated and checked → shuttle seat → measured
silicon. **Current position: spec proposed, awaiting ratification** (bitcell question
answered, porting plan recorded).

## Repo layout

```
spec/          ratified spec, porting plan + decision records
design/        bitcell and periphery schematics
sim/           testbenches + PVT corner results (ngspice)
layout/        GDS + DRC/LVS reports (klayout-tools driven)
measurements/  silicon characterization (empty until tape-out)
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).

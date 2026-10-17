# sg13g2-sram — agent instructions

Open-source canary block: an SRAM macro on IHP SG13G2, a 130 nm SiGe BiCMOS
open PDK, built and verified by AI agents. A port of `gf180-sram`.

- **PDK**: IHP SG13G2 (open PDK, IHP-GmbH/IHP-Open-PDK). Analog: xschem +
  ngspice (the PDK's compact models load through OSDI). Layout, DRC, LVS and
  view generation through klayout-tools (`klt`).
- **The PDK is the variable, not the design.** `gf180-sram` is the origin
  and master for the spec structure, margin definitions, statistical
  treatment and harness. Inherit those; re-derive only what is device-level
  (bitcell sizing, periphery, supply, corners, timing). Departures go
  through decision records. A finding about the origin is filed on
  `gf180-sram`, not only written down here.
- **First question, before the spec**: is SG13G2's SRAM bitcell usable as a
  standalone, tileable primitive, or only inside the shipped `sg13g2_sram`
  macros? Resolve it and record it in `spec/` before ratification, as the
  origin did.
- **The array is the point, and the risk.** Array generation, macro-level
  LVS, hierarchy handling and LEF/Liberty generation on a deck newer than
  the origin's are the tool surface under test. Expect the deck to have gaps
  a dense memory array is first to find.
- **Scope discipline.** No `consumes:` edge is declared. The shipped
  `sg13g2_sram` 256 × 32 macro is the comparison point, not a part this repo
  wraps. Free SRAM generators are references: cite, do not reimplement. The
  harness comes from `gf180-sram` by pinned reference (`reuse.lock.json`,
  `REUSE.md` in `2AMLogic/2am`).
- **Friction protocol (the canary's job)**: every time klayout-tools is
  awkward, missing a capability, or wrong for what you need, file an issue at
  `2AMLogic/klayout-tools` describing the tool gap generically — that tracker
  is scoped to the tool, so keep design-specific detail out of it and describe
  the gap, not the design.
- **Verification is the product**: no claim without a testbench. PVT corners
  on every recorded result; stability margins also need Monte Carlo
  evidence; `sim/` results are append-only evidence.
- Spec changes go through `spec/` with a decision record; agents do not relax
  the ratified spec to make results pass. `spec/porting-plan.md` names the
  `gf180-sram` commit it read.

<!-- BEGIN LOOM ORCHESTRATION -->
This repository uses [Loom](https://github.com/rjwalters/loom) for AI-powered development orchestration — see the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of that guide to `.loom/CLAUDE.md`.

Work is coordinated through `loom:` labels on issues and pull requests, and the same roles run either under `loom-daemon` or by hand in an attended session — daemon mode is optional. Create the labels once with `.loom/scripts/sync-labels.sh` (an install ships `.github/labels.yml` but does not create the labels on the forge). A pull request ready for review carries `loom:review-requested`; Judge reviews it and applies `loom:pr` (approved) or `loom:changes-requested`; Doctor fixes a `loom:changes-requested` pull request and returns it to `loom:review-requested`. Only a `loom:pr` pull request gets merged, and always via this repo's merge script (`.loom/scripts/merge-pr.sh`) — never a raw forge merge command such as `gh pr merge`. Full state machine: `.loom/docs/label-state-machine.md`.
<!-- END LOOM ORCHESTRATION -->

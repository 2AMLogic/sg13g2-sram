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

# spec

Proposed specification for the SG13G2 SRAM macro. Nothing here is ratified
until an operator approves the PR that landed it.

| File | What it is |
|---|---|
| [`sram.md`](sram.md) | The target spec: every parameter as target / stretch, the 45-corner set, the reference row for the shipped macro |
| [`porting-plan.md`](porting-plan.md) | Every item inherited from `gf180-sram` (with its commit) or re-derived (with the reason) |
| [`bitcell-decision.md`](bitcell-decision.md) | The first question: is the SG13G2 bitcell usable standalone? |
| [`write-pulse-width-decision.md`](write-pulse-width-decision.md) | The fixed write-pulse width for write margin |
| [`access-time-target-decision.md`](access-time-target-decision.md) | Proposed access-time pass threshold: typical clock-to-Q no worse than the comp's 3.05 ns |
| [`signoff-tooling-decision.md`](signoff-tooling-decision.md) | Sign-off envelope and table tooling from `gf180-sram` is not ported |
| [`ratification-review-decision.md`](ratification-review-decision.md) | Post-hoc two-key review of `sram.md` as merged in #7: keys installed under `ratification/`, review not yet run |

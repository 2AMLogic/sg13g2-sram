# Decision record: access time is graded against the shipped comp's typical clock-to-Q

**Status**: Proposed, 2026-10-29 (not self-ratified)
**Resolves**: #73, "spec: no access-time target value"
**Answers**: market-key finding F1 in the post-hoc ratification review (#37)
**Origin**: operator ruling 2026-10-29 (option a, attended decision q135).
`gf180-sram` set no comp-relative access target; this is a departure from
"recorded, no pass threshold", argued here.

## Question

`spec/sram.md` records access time with no pass threshold, so a buyer cannot
compare the macro to the shipped `RM_IHPSG13_1P_256x32_c2_bm_bist` (3.05 ns
typical clock-to-Q). Should access time get a pass threshold, and what is it?

## Answer

**Threshold, relative to the comp, no absolute figure invented.**

- **Graded point**: typical corner (`mos_tt`, 25 °C, 1.20 V). Clock edge to
  valid `DOUT[0]` (50 % of VDD clock edge to 50 % of VDD output rise, the bench's
  stated crossings) **no worse than 3.05 ns**, the comp's typical figure.
  Ratio 1.0 against the comp.
- **Context, not graded**: the comp's fast and slow figures, **1.876 ns** and
  **5.126 ns** (`spec/sram.md` "Reference row", Liberty, read 2026-10-17).
  The slow corner `mos_ss`, 125 °C, 1.08 V is measured in this repo's set and
  its ratio to 5.126 ns is reported next to the result. It does not gate.
- **All other corners**: recorded, as today. A corner's access time does not
  fail that corner.
- **Revision rule**: if the first measurement misses 3.05 ns, the threshold
  changes only through a new decision record. It is never relaxed in place,
  and never edited against a failing result.

## Rationale

1. **One graded point, because that is where the comp is comparable.** The
   comp ships three Liberty corners: fast (1.32 V, -55 °C), typical
   (1.20 V, 25 °C) and slow (1.08 V, 125 °C). The typical and slow ones
   match a voltage and temperature in this repo's 45-corner set; the fast one
   is at -55 °C and the set bottoms out at -40 °C. Only typical has an
   unambiguous process match (`mos_tt`).
   Grading the other 44 corners would need a comp figure at each, and none
   exists; deriving one would invent a number.
2. **Why not grade fast and slow too.** Ratio 1.0 at `mos_ss` / 125 °C / 1.08 V
   would be a defensible reading, but the comp's process corner naming does not
   map one-to-one onto `mos_*`, so the ratio there would be a judgement about
   what the comp's "slow" means. It is reported so a reader can see it, not
   used to pass or fail. A later record can promote it to graded once the
   mapping is argued.
3. **Why 1.0, not a margin either way.** The ruling asks for a figure "no
   worse than" the comp. A looser ratio would let the macro be slower than the
   part a buyer compares it to; a tighter one has no basis in anything
   measured. 1.0 invents nothing.
4. **Comparable condition.** The comp figure is the lowest slew and load
   `cell_rise` entry for bit 0. The macro measurement must use a comparable
   condition: bit 0, rising output, the bench's own clock slew, and a load no
   heavier than the Liberty's lowest-load entry. The bench is schematic level,
   with no wire parasitics (`sim/array/bench_access.cir` header), so a pass
   at this stage is a pre-layout pass and the record does not say otherwise.
5. **Statistical treatment is unchanged.** Access time is not classified as
   statistical; no Monte Carlo is added.

## How the row is graded

- **Testbench**: `sim/array/bench_access.cir`, run through
  `sim/array/run_array.sh`. It reports clock edge to valid Q for the rising
  read in the last cycle.
- **Grading**: at the `mos_tt`, 25 °C, 1.20 V corner the row passes if the
  reported clock-to-Q is at most 3.05 ns, and fails otherwise. The
  `mos_ss`, 125 °C, 1.08 V ratio to 5.126 ns is reported alongside. Every other
  corner records its value.
- **Not claimed here**: this record contains no measurement and cites no
  result. Whether the macro meets 3.05 ns is unknown until the bench is run.

## Open, verify at first run

- The first access-time result is compared with 3.05 ns as written. A miss
  is an open result and a new record, not an edit to this one.
- The comp figures are as read in `spec/sram.md`. They are not re-checked
  against the Liberty here (#76).

## What this record changes

If ratified: the `spec/sram.md` access-time bullet, the corner-pass sentence
and the signoff definition reference this record. Until ratified they cite it as
Proposed and the recorded-only rule stands as the operator's pending change.
Area, minimum pulse and power targets are #74 and are not touched.
Ratification follows the usual path: this record merges as Proposed, then the
operator ratifies through the key reviews (#37).

## References

- `spec/sram.md` "Reference row" (comp figures, read 2026-10-17)
- `spec/write-pulse-width-decision.md` (the 1 ns write pulse; unchanged)
- `sim/array/bench_access.cir`, `sim/array/run_array.sh`
- #37 (F1), #73, #74, #76

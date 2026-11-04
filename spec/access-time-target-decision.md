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
  valid macro output pin `Q[0]`, as the bench grades it: CLK 50 % of VDD rise
  to `Q[0]` crossing 90 % of VDD (read of 1; 10 % for the read of 0), per
  `access_measurements()` in `sim/array/array_post.py`. **No worse than
  3.05 ns**, the comp's typical figure. Ratio 1.0 against the comp. The comp's
  Liberty delay is measured 50 % to 50 % (`output_threshold_pct_rise 50`); a
  90 % crossing is later than a 50 % one, so the bench figure is conservative
  against the comp's definition, not flattering.
- **Context, not graded**: the comp's fast and slow figures, **1.876 ns** and
  **5.126 ns** (`spec/sram.md` "Reference row", Liberty, read 2026-10-17).
  The comp's slow point (1.08 V, 125 °C) matches `mos_ss`, 125 °C, 1.08 V in
  this repo's set; its ratio to 5.126 ns is reported next to the result. It
  does not gate. It is not this macro's worst access corner: on the committed
  records the slowest read is `mos_ss`, 1.08 V, 25 °C at 3.2241 ns
  (3.2206 ns at -40 °C, 3.0578 ns at 125 °C), because at 1.08 V on these LV
  devices delay is V_T-dominated and rises as temperature falls.
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
   `cell_rise` entry of the single `A_DOUT[31:0]` bus arc (`related_pin
   A_CLK`, `rising_edge`), which covers all 32 bits. The macro measurement is
   bit 0 (`Q[0]`), rising output, the bench's own clock slew (100 ps edges,
   within about 6 ps of the like-for-like comp entry) and no load on `Q[0]`
   (the comp's lowest-load entry is 0.0008 pF, about 2 ps). The bench is schematic level,
   with no wire parasitics (`sim/array/bench_access.cir` header), so a pass
   at this stage is a pre-layout pass and the record does not say otherwise.
5. **Statistical treatment is unchanged.** Access time is not classified as
   statistical; no Monte Carlo is added.

## How the row is graded

- **Testbench**: `sim/array/bench_access.cir`, run through
  `sim/array/run_array.sh`. It reports CLK 50 % to `Q[0]` 90 % (read of 1) and
  10 % (read of 0) of VDD, per the definition string `cmd_access()` writes
  into every record.
- **Grading**: at the `mos_tt`, 25 °C, 1.20 V corner the row passes if the
  reported clock-to-Q is at most 3.05 ns, and fails otherwise. The
  `mos_ss`, 125 °C, 1.08 V ratio to 5.126 ns is reported alongside. Every other
  corner records its value.
- **Evidence at this head, not graded here**: two 45-corner access records are
  committed, `sim/array/records/20261028T135153Z/` and
  `sim/array/records/20261028T144609Z/` (`corner_count 45`, `any_fail false`).
  At `mos_tt`, 25 °C, 1.20 V they report `read1_access_ns` 2.0894 and
  `read0_access_ns` 1.7559. This record does not grade them: it proposes the
  threshold, and grading happens when it is ratified and the bench is next
  run under it. They are pre-layout (schematic level, no wire parasitics).

## Open, verify at first run

- The first access-time measurement graded under this record is compared with
  3.05 ns as written. A miss is an open result and a new record, not an edit
  to this one.
- The comp figures are as read in `spec/sram.md`; the 3.05, 5.126 and
  1.876 ns values were re-derived from the public Liberty at PDK tag `v0.3.0`
  during review. The bus-arc wording in `comps/sram.md` is #76.

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

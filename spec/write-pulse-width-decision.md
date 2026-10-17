# Decision record: write margin is measured against a fixed 1 ns write pulse

**Status**: Proposed, 2026-10-17 (not self-ratified)
**Resolves**: #2, "Write-pulse width: the value for this PDK, with its rationale"
**Origin**: `gf180-sram` `spec/write-pulse-width-decision.md` @ `d0bacc0`
(rule inherited, value re-derived)

## Question

The origin ratified that write margin is measured against a fixed, stated
write-pulse width, with no independent macro timing target, and set that
width to 2 ns. What is the value here?

## Answer

**Rule inherited unchanged**: no independent clock-period or cycle-time
target is ratified; write margin is measured against one fixed, stated
wordline pulse. **Value: 1 ns** (wordline high, bit lines driven), at every
corner in the 45-corner set.

## Rationale

1. The origin's 2 ns was a testbench window chosen at 180 nm / 3.3 V, then
   checked afterwards against its measured write access time (about 85 ps at
   the slowest corner, a margin of about 23×). Neither number transfers to
   130 nm / 1.2 V, so the check is re-run here, not the number copied.
2. The reference macro bounds the scale. Its Liberty (typ 1.20 V / 25 °C)
   gives clock-to-output about 3.05 ns, and a clock minimum pulse width of
   0.21 ns (typ), 0.40 ns (slow 1.08 V / 125 °C), 0.12 ns (fast). The
   internal wordline pulse of a macro that is clocked at that rate is
   well under 3 ns, so a pulse in the 1 ns range is in family with what
   the foundry's own array sees, and well above the foundry's minimum clock
   pulse.
3. 1 ns is chosen to be long compared with a bitcell flip time, so the
   measurement observes a completed write, and short enough that a cell
   that only flips given a very long pulse is not reported as having
   margin. It is a stated value, not a derived one. This record does not
   claim 1 ns was derived from item 2.

## Open, verify at first run

- The pulse is confirmed only once a write-margin run exists. At that
  point the first run must record flip time at the slowest corner
  (`mos_ss`, 125 °C, 1.08 V) and show it is well inside 1 ns. If it is
  not, the value goes up through a new decision record, not an edit
  against the failing result.
- A sensitivity sweep at 0.5 / 1 / 2 ns on the three worst corners is
  recorded with the first write-margin run, so the margin's dependence on
  the stated width is visible. The sweep does not change the ratified
  value.

## What this record changes

`spec/sram.md` write-margin bullet states the 1 ns window. Nothing else.

## References

- `gf180-sram` `spec/write-pulse-width-decision.md` @ `d0bacc0`
- `RM_IHPSG13_1P_256x32_c2_bm_bist_{fast_1p32V_m55C,typ_1p20V_25C,slow_1p08V_125C}.lib`
  in `~/share/pdk/ihp-sg13g2/libs.ref/sg13g2_sram/lib/`

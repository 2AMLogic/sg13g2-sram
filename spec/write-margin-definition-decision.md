# Decision record: what "write margin" means

**Status**: Proposed, 2026-10-29 (not self-ratified)
**Resolves**: #71, EE-key finding F4 on #37 (write margin under-determined in `spec/sram.md`)
**Origin**: `gf180-sram` margin definitions (rule inherited); this record only
pins what the `sim/` code in this repo already measures.

## Question

`spec/sram.md` says write margin is the "minimum bit-line / write-driver drive
that flips the cell within a fixed 1 ns write pulse. Strictly positive." That
states no unit, no sign, no zero point, no resolution, no flip criterion and no
no-flip rule, and "minimum drive" reads opposite to what the benches report
(the highest bit-line low level that still flips). What exactly is measured?

## Answer

This record describes the definition `sim/bitcell/` and `sim/array/` use today.
It changes no bench, grid, corner set or pass rule, and relaxes no margin.

1. **Quantity and unit**: volts, on the bit-line **low** level (the side of the
   bit-line pair being pulled down; the other bit line is held at VDD).
2. **Trip level, `L_trip`**: the **highest** constant bit-line low level at which
   a stand-alone cell, starting from the opposite value, flips. A weaker drive
   is a higher low level, so a larger `L_trip` means the cell is easier to
   write. "Minimum drive" in the spec is this: the weakest drive that still
   writes.
3. **Search grid**: 33 levels, `L_k = 25 mV * k`, k = 0..32 (0 to 0.8 V), as
   absolute volts that do **not** scale with the supply corner
   (`BL_STEP_V`, `N_LEVELS` in `sim/bitcell/bitcell_post.py` and
   `sim/array/array_post.py`). If the top level (0.8 V) still flips, the
   result is flagged saturated and is a lower bound, not a value.
4. **Resolution**: 25 mV. `L_trip` is a quantisation of the sweep, not a
   measurement noise floor.
5. **Flip criterion** (a level "flips"): the cell reads the written value at the
   end of the 1 ns wordline pulse **and** still reads it at a later check time
   with the wordline off. Bitcell bench: 1.3 ns and 2.5 ns absolute
   (`sim/bitcell/bench_write.cir`). Array bench: 1.95 ns and 3.4 ns absolute
   (`sim/array/bench_write.cir`, `T_END_NS`, `T_FINAL_NS`). The pulse is the
   1 ns of `spec/write-pulse-width-decision.md`.
6. **Sign convention and zero point**: for the cell-level bench, margin is
   `L_trip`. Margin **0** means the cell flips only with the bit line at 0 V;
   **strictly positive** means the bit line need not reach 0 V. Margin 0 is
   not positive, so it fails the spec's "strictly positive".
7. **No-flip rule**: if no level flips, even at 0 V, the margin is `null`. A
   `null` margin is not positive and counts as failing. It is never dropped
   from a result and never recorded as 0 or as a negative number. A corner with
   a missing or non-numeric measurement also counts as failing.

## Which bench is the signed-off one

Two benches carry the name, and they measure different things.

- **Array bench (signed off)**: write through the real write driver in the real
  column (`design/column/column.spice`). Margin per case is
  `write_margin_v = L_trip - L_drv`, where `L_trip` is item 2 (from 33
  stand-alone cells of the column's own bitcell at the same corner) and
  `L_drv` is the bit-line low level the driver actually holds in situ at the
  end of the pulse. It is positive iff the driver pulls the bit line below the
  level the cell needs, and it **can be negative** (driver too weak). Both
  write-0 and write-1 are measured, because the drivers are asymmetric, and the
  recorded margin is the **worse (smaller) of the two**. The corner passes only
  if, in addition, the cell flipped within the pulse, the value holds at the
  later check time, and the half-selected cell is retained
  (`verdict_write` in `sim/array/array_post.py`). Only `L_trip` carries the
  25 mV quantisation; `L_drv` is a continuous measurement.
- **Bitcell bench (cell-level companion)**: bit line forced directly, no
  driver. It reports `L_trip` itself (item 2), so it answers "how weak a drive
  can this cell tolerate", not "does the real driver have margin". It is
  evidence about the cell, and does not stand in for the array margin.

## Monte Carlo

The 25 mV resolution of `L_trip` is a quantisation that the Monte Carlo
treatment (#68) must carry into its Cpk, sigma-to-spec and yield statements. A
per-sample margin takes values on a 25 mV lattice offset by a continuous
`L_drv`, in the array bench, or sits exactly on the lattice, in the bitcell
bench. The statement of any statistic on it must say which, and must not claim
a precision finer than the quantisation without saying how it was handled.

## What this record changes

`spec/sram.md` write-margin bullet states this definition and links this
record. Nothing else. `spec/sram.md` stays Proposed. Existing `sim/` records
are not edited (append-only), and no pass rule changes.

## References

- `sim/bitcell/README.md` (`bench_write`), `sim/bitcell/bitcell_post.py` `cmd_write`
- `sim/array/README.md`, `sim/array/array_post.py` `verdict_write`, `cmd_write`
- `spec/write-pulse-width-decision.md`

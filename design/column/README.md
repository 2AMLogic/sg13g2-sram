# column

One I/O column of the macro: bit-line precharge/equalize, a 2:1 column mux, a
latch sense amp, a write driver, and the bitcell tiled on each bit line.
Schematics are xschem on `sg13_lv_nmos` / `sg13_lv_pmos`, L = 130 nm; each
`.spice` is derived with `klt netlist --block` (`../README.md`,
`../netlist.sh`). Inventory: `INVENTORY.md`.

## Decision: mux 2, 128 cells per bit line

The organization stays 256 words × 32 bits (`spec/sram.md`). Rows per bit line
is 256 / mux, so the mux ratio fixes the bit-line load. **Mux 2: 128 cells per
bit line, 64 physical columns, address split 7 row bits + 1 column bit.** This
matches the comparison macro's mux (`spec/sram.md` reference row). Rejected:
mux 1, where the mux degenerates to a pass gate and the 256-cell bit line is a
heavier load than the comparison point. Not simulated: the load argument is
reasoning, not a measurement. #24 inherits the split.

## Blocks

| Block | Ports (netlist order) | Devices |
|---|---|---|
| `precharge` | `PRE_B BL BLB VDD VSS` | 3 PMOS 1.0 µm: two pull-ups to VDD, one equalizer |
| `column_mux` | `SEL0 SEL0B SEL1 SEL1B BL0 BLB0 BL1 BLB1 BLM BLBM VDD VSS` | 4 transmission gates, NMOS 2.0 µm + PMOS 2.0 µm |
| `sense_amp` | `SAE BLM BLBM OUT OUTB VDD VSS` | 2 PMOS isolation 2.0 µm (gate `SAE`), cross-coupled latch NMOS 1.0 µm / PMOS 1.0 µm, tail NMOS 2.0 µm (gate `SAE`) |
| `write_driver` | `WE DIN BLM BLBM VDD VSS` | inverter (0.5 µm), two 2-high NMOS stacks 3.0 µm: `WE`·`DIN` pulls `BLBM` low, `WE`·`DINB` pulls `BLM` low |
| `column` | `PRE0_B PRE1_B SEL0 SEL0B SEL1 SEL1B SAE WE DIN WL WLU DOUT DOUTB VDD VSS` | 2 bit-line pairs × 128 `bitcell`, 2 `precharge`, `column_mux`, `sense_amp`, `write_driver` |

The cell is `../bitcell/bitcell.sch` at the reference sizing, unchanged. In
`column`, `XC0`/`XC1` are the selected row's cell on each pair (`WL`);
`XU0[126:0]`/`XU1[126:0]` are the other 127 rows of each pair, all on `WLU`
(held low). The 127 cells of a pair share one `Q`/`QB` node pair (`UQ`/`UQB`):
electrically 127 identical cells in the same state, which is the worst data
pattern for leakage and keeps the bench's initial conditions to four nodes per
pair. Separate per-row `WL` nets are #24's wiring. Read polarity: a stored 1
(`Q` high) discharges `BLB`, `DOUT` follows `BL`, so `DOUT` = stored value; a
write drives `BLM`/`BLBM` so that `Q` takes `DIN`.

## Write driver sizing and its source

**Status: justified at nominal (mos_tt, 1.20 V, 27 °C) by a width sweep; corner and
Monte Carlo margin are #26's.** The four driver NMOS stack devices were swept with the
write bench (real bitcell, 127 unselected rows per bit line, half-selected cell present;
`sim/column/run_sizing.sh`, record `sim/column/sizing/20261028T074902Z/`). Flip time from
the 50 % point of the wordline edge, worst of the two written values, against the 1 ns
pulse (`spec/write-pulse-width-decision.md`):

| stack width | 0.15 µm | 0.3 µm | 0.5 µm | 1.0 µm | 2.0 µm | 3.0 µm |
|---|---|---|---|---|---|---|
| flip time | no flip | 0.96 ns (fails) | 0.54 ns | 0.25 ns | 0.12 ns | 0.09 ns |

The 3.0 µm stacks flip the cell in 0.09 ns, about 11x inside the pulse; the smallest
passing width at nominal is 0.5 µm (1.8x inside). 3.0 µm is kept: it leaves room for
slow corners, low supply and cell mismatch, which this nominal sweep does not cover.
Shrinking it for area is a decision for the corner and Monte Carlo results in #26, not
this nominal bench. The 0.15 µm run is also the negative control (the bench detects a
driver too weak to write).

## Sources

The sense amp is a standard latch-type amplifier with a sense-enable. No
shipped-macro netlist or generator was copied (`CLAUDE.md`, scope discipline).

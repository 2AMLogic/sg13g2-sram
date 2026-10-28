# sim/array

Array-level benches over the spec's 45 corners (`spec/sram.md`: 5 process x 3 supply x
3 temperature). Organization: mux 2, 128 cells per bit line, 2 bit-line pairs per I/O.
Everything is **simulated** (schematic netlists, no parasitics).

| Bench | Measures | Netlist under test |
|---|---|---|
| `bench_snm.cir` | read SNM in situ: the selected cell with 127 unselected cells, precharge, mux and sense-amp input on its bit-line pair | `design/column/column.spice` |
| `bench_write.cir` | write margin through the real write driver, 1 ns wordline pulse (`spec/write-pulse-width-decision.md`) | `design/column/column.spice` |
| `bench_access.cir` | access time (CLK edge to valid `Q`) for reads of 1 and 0, and write completion (cell flip after the CLK edge) for writes of 1 and 0; full control, decode and latches, one real bit slice, the other 31 as load | `design/macro/macro.spice` |

- `array_post.py`: builds the `klt sim` requests (45-corner grid or `--typical`), generates
  `bench_access.cir` from `macro.spice` (`gen-access`, `--check` in the run script), builds
  the negative-control netlists, and extracts per-corner results. A corner with a missing or
  non-numeric measurement counts as failing; it is never dropped. A margin is `null` when
  the cell did not flip. `test_array_post.py` tests all of it without a simulator
  (`python3 -I sim/array/test_array_post.py`).
- `run_array.sh [--typical]`: netlist freshness check, three negative controls
  (beta 0.25 cell must read a lower SNM; a 0.15 um write driver must fail the write bench and
  the access bench), the three grids, then `records/<UTC>/` (append-only).

## Backend

Batch only (`klt sim --backend batch`). A failed submit exits 6 and does not fall back to a
local grid. Local ngspice 42 cannot load the OSDI v0.4 models (`sim/bitcell/README.md`).

## Records

`records/<UTC>/record.json` holds the worst margin per bench with its corner, the failing
corners, the batch job ids, the negative-control detections and what is not established.
Failing corners are recorded, not hidden; the script exits 0 when the run completed and all
negative controls were detected.

Not established here: Monte Carlo, parasitic-extracted timing, wordline and bit-line wire RC.
Margins are recorded, not graded against a spec number.

## Status

Latest grid record: `records/20261028T135153Z/` (45 corners, batch fleet, runner klt 0.8.0, ngspice 42; all
corners pass, all three negative controls detected). Worst read SNM in situ 145 mV
(mos_fs/1.080V/125C); worst write margin 250 mV (mos_sf/1.080V/-40C);
slowest read-of-1 access 3.2241 ns (mos_ss/1.080V/25C). A second record from the item 9 attestation
run (`run_all.sh`) sits beside it; records are never overwritten.

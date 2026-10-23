# bitcell

`bitcell.sch` is a 6T SRAM cell (subcircuit `bitcell`, ports
`BL BLB WL VDD VSS Q QB`) on `sg13_lv_nmos` / `sg13_lv_pmos`, L = 130 nm.
`bitcell.spice` is derived from it by `klt netlist` (see `../README.md`).
`Q`/`QB` are ports so a testbench can break the storage loop for a butterfly
measurement; in an array they are internal.

| Device | Role | Model | W | L |
|---|---|---|---|---|
| `MN0`, `MN1` | pull-down | `sg13_lv_nmos` | 300 nm | 130 nm |
| `MP0`, `MP1` | pull-up | `sg13_lv_pmos` | 150 nm | 130 nm |
| `MN2`, `MN3` | access | `sg13_lv_nmos` | 300 nm | 130 nm |

Beta ratio (pull-down : access) is 1.0. This is the reference point of
`spec/bitcell-decision.md`, taken as is: no resize happened here. Resizing is a
sweep with its own results (and a decision record if the spec changes).

## Source of the sizes

Re-read from the PDK checkout `~/share/pdk/ihp-sg13g2` (`klt pdk` version stamp
`fetched:0.3.0`, release v0.3.0), file
`libs.ref/sg13g2_sram/cdl/RM_IHPSG13_1P_256x32_c2_bm_bist.cdl`, subcircuit
`RM_IHPSG13_256x32_c2_1P_BITKIT_CELL`, lines 67-77:

- `MN0`, `MN1`, `MN2`, `MN3`: `sg13_lv_nmos w=300.0n l=130.00n` (lines 69-72)
- `MP1`, `MP0`: `sg13_lv_pmos w=150.00n l=130.00n` (lines 73-74)
- `R0`, `R1`, `R2`: `lvsres` stitching resistors (lines 75-77), ignored: layout
  artifacts, not circuit elements (`spec/bitcell-decision.md` evidence 1).

Differences from the foundry cell, deliberate: bulks are tied to `VSS`/`VDD`
(the foundry cell has separate `PW`/`NW` ports), and the foundry's split bit-line
and wordline halves are one net each. Only the cell topology and sizes are
used; no foundry geometry is copied (`spec/bitcell-decision.md` item 6).

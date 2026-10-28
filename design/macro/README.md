# macro

The 256 x 32 macro top (`macro.sch`) and the two array blocks under it. Pins, as in
`spec/sram.md`: `A[7:0] CEN CLK D[31:0] Q[31:0] GWEN WEN` plus one rail, `VDD`/`VSS`.

## Organization

Mux 2 (`design/column/README.md`): 128 rows x 64 physical columns, so the row decoder is
**7 bits, 128 wordlines**, not 8 bits and 256: `A[0]` is the column select, `A[7:1]` the
row. 256 wordlines would be a mux-1 array, the 256-cell bit line the column decision
rejected.

| Block | Role |
|---|---|
| `bl_pair` | the 128 `bitcell`s of one bit-line pair, one per `WL[r]` (vector instance `XB[127:0]`) |
| `bit_slice` | one I/O bit: 2 `bl_pair`, 2 `precharge` (shared `PRE_B`), `column_mux`, `sense_amp`, `write_driver` |
| `macro` | `addr_latch`, `control`, `row_decoder`, `data_latch`, 32 `bit_slice` (vector `XS[31:0]`), `out_latch` |

`bit_slice` reuses the column path blocks and the bitcell unchanged; it does not
instantiate `column/column.sch`, which hard-wires one selected row (`WL`) and 127 shared
unselected cells (`WLU`) for the bench.

## Protocol (first pass; timing closure is item 9)

- `addr_latch`/`data_latch`: transparent while `CLK` is low, hold while it is high, so the
  inputs are captured at the rising edge.
- `control`: `ACT = CLK & ~CEN`; `PRE_B = ACT` (precharge during the low phase and when
  disabled); `WLEN = ACT & delayed ACT` (wordline after precharge releases, falls with
  `CLK`); `SAE = WLEN & delayed WLEN & read`; `WE = WLEN & write`; write = `GWEN` and `WEN`
  both low. `SEL0/SEL0B/SEL1/SEL1B` decode the latched `A[0]`.
- `out_latch`: transparent while `SAE` is high, so `Q` holds the resolved value until the
  next read.
- `row_decoder`: `A[2:0]` -> `X[8]`, `A[6:3]` -> `Y[16]`, `WL[8j+k] = X[k] & Y[j] & WLEN`.

Sizing is a first pass.

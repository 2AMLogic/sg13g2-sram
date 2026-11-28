# Decision record: the write mask is per-bit `WEN[31:0]`

**Status**: Proposed (not self-ratified)
**Resolves**: #126, "`WEN` is a scalar in the netlist; the origin's interface is per-bit `WEN[31:0]`"
**Origin**: `gf180-sram` `spec/macro-interface-decision.md` (row 4), `design/check_macro_pins.py`,
`spec/periphery-architecture.md`. Not checked out at the commit `spec/porting-plan.md` names (`d0bacc0`);
read through `gh search code` on `2AMLogic/gf180-sram`.

## Question

`spec/sram.md` § Ports says to keep the origin's `GWEN`, `WEN` and gives no width. The committed
netlist had a scalar `WEN`, one `WE = WLEN & write` shared by all 32 `bit_slice`s, so no per-bit
mask existed. What is the contract?

## Answer

**Per-bit `WEN[31:0]`, active low; `WEN[i]` gates `D[i]` into slice `i`.** A write happens in slice
`i` only when `GWEN` and `WEN[i]` are both low. `GWEN` semantics are unchanged (high = read).

Why: `spec/sram.md` says the PDK is the variable and the interface is not, and no reason was found for
it to differ. The Verilog/CDL target views ratified by #79 describe the origin interface, and the
shipped `sg13g2_sram` macro has the same function (`A_BM[31:0]`). Rejected: keep a scalar and record a
departure; it would need its own record and loses the byte-mask function.

## Implementation (design/)

- **Latched mask placement: with the data.** `data_latch` latches `WEN[31:0]` as `WENL[31:0]` with the
  same `CLK`-low-transparent latches as `D`, so the mask and the data it qualifies are captured at the
  same edge and obey the same timing. The scalar `WEN` latch is removed from `addr_latch`, and
  `control` no longer takes a mask (`WRITE = ~GWENL`). Chosen over 32 latches in `addr_latch`
  because the mask is per-data-bit state, not control state; the sim showed no timing reason to do otherwise.
- **Mask gate per slice**: `WE_i = nor2(inv(WE), WENL[i])` in front of the slice's write driver.
  `bit_slice` gains a `WEN` port.
- **Write-pulse margin** (`spec/write-pulse-width-decision.md`): the mask gate adds an inv + nor2 on
  the write path, and removes the `nor2` that combined `GWENL`/`WENL` in `control`. Measured at all
  45 corners (record `20261101T180845Z`), the slowest write completion (clock edge to cell flip) is
  2.3389 ns (write 1) and 2.2766 ns (write 0), both at `mos_ss`/1.08 V/-40 C, against 2.5509 and
  2.4398 ns in the previous record (`20261028T144609Z`): not slower. The 1 ns write-margin bench
  drives the cell directly and is unchanged; write margin worst case is 0.2498 V (`mos_sf`/1.08 V/-40 C), identical to the previous record, no failing corner.
  This is schematic level, no wire parasitics.

## Evidence

`sim/array/records/20261101T180845Z/`: 45 corners, one `klt sim` request per bench on the batch
fleet. The access bench gained a masked write (GWEN low, `WEN[0]` high, D[0] = 0) followed by a read:
bit 0 keeps its 1 at every corner (smallest stored cell differential 1.08 V at the 1.08 V corner).
Negative control: with every slice's mask gate tied to enabled (`negctl/macro_nomask.spice`) the same
bench fails (`masked_write_leaves_bit` false), so the check discriminates. The bench drives
`WEN[0]` high for one write and `WEN[1..31]` low; the other 31 slices are load only (with their mask
gates), so the full-word and all-high cases are covered by schematic equivalence, not simulated per bit.

## What this record changes

`spec/sram.md` ratified text is untouched. The Ports row's silence on the width is resolved here;
a one-line clarification, if wanted, is a follow-up spec change by an operator.

## Not done (follow-ups)

- Layout, LEF and socket pin split to 32 `WEN` pins (`layout/sram_256x32/generate.py`, `macro.lef`,
  `macro.socket.json`, LVS against the new netlist) is #108's surface; the layout still has a single `WEN`
  pin and no longer matches `macro.spice` until that lands.
- Monte Carlo on the mask path, parasitic-extracted timing.
- `design/netlist.sh --check` reports `control`, `bit_slice` and `macro` stale on `main` as well (checkout-
  specific `sym_path`/`sch_path` comment lines, see `sim/array/run_array.sh`); it cannot gate here.

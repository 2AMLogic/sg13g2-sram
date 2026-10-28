# design

Schematics (xschem) and the SPICE netlists derived from them.

- `bitcell/`: the 6T bitcell at the reference sizing (hold/read SNM and write
  margin: `sim/bitcell/`).
- `column/`: one I/O column (precharge, 2:1 mux, sense amp, write driver, cells
  tiled 128 per bit line); see `column/README.md` and `column/INVENTORY.md`.
- `gates/`: leaf logic (`inv`, `inv_x4`, `nand2/3/4`, `nor2`) shared by the blocks below.
- `decoder/`: 7-bit row decoder, 128 wordlines (`predec3`, `predec4`, `wl_driver`,
  `wl_drivers`, `row_decoder`).
- `latches/`: `dlatch` and the address/control (`addr_latch`), write-data
  (`data_latch`) and read-data (`out_latch`) latch banks.
- `control/`: `control`, the clock-derived timing (precharge, wordline enable, sense
  enable, write enable, column selects).
- `macro/`: `bl_pair` (128 cells on one bit-line pair), `bit_slice` (one I/O bit) and
  `macro`, the 256 x 32 top; see `macro/README.md`.
- `bitcell/bitcell.sym`, `*/*.sym`: hand-written symbols for hierarchy.
- `xschemrc`: symbol search path for `klt netlist --rcfile` (xschem's
  `devices/` plus the PDK's `sg13g2_pr` symbols; PDK from `PDK_ROOT`/`PDK`).

Committed netlists are derived artifacts. Regenerate all of them, or check for
drift (exit 3 if any is stale), with `design/netlist.sh [--check]`; per file that
runs:

```bash
source sim/harness/common/env.sh
klt netlist design/bitcell/bitcell.sch -o design/bitcell/bitcell.spice --block \
  --rcfile design/xschemrc --pdk "$PDK" --pdk-root "$PDK_ROOT"          # add --check to verify
```

Every source and derived file is listed in `attest/item1.json`, the T1 item 1
inventory (`klt signoff --attest 1`, envelope `attest/item1.envelope.json`).
Symbols are referenced as `<block dir>/<cell>.sym`, resolved through `xschemrc`'s
library path, so a schematic netlists the same whether it is the top or nested.
A bus port is drawn as one scalar pin per bit (`WL[127]` ... `WL[0]`): `klt netlist`
joins a bus port with commas in `.subckt`, which ngspice mis-maps once a subcircuit
has two or more bus ports.

Never run `xschem` directly: `klt netlist` forces the headless flags and bounds
the run. xschem writes the schematic's absolute path into line 1 of the
netlist; the committed file keeps the repo-relative path (`--check` ignores that
comment).

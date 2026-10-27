# design

Schematics (xschem) and the SPICE netlists derived from them.

- `bitcell/`: the 6T bitcell at the reference sizing (hold/read SNM and write
  margin: `sim/bitcell/`).
- `column/`: one I/O column (precharge, 2:1 mux, sense amp, write driver, cells
  tiled 128 per bit line); see `column/README.md` and `column/INVENTORY.md`.
- `bitcell/bitcell.sym`, `column/*.sym`: hand-written symbols for hierarchy.
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

Never run `xschem` directly: `klt netlist` forces the headless flags and bounds
the run. xschem writes the schematic's absolute path into line 1 of the
netlist; the committed file keeps the repo-relative path (`--check` ignores that
comment).

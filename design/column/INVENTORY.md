# column inventory

Sources and derived netlists of the column path, in a form #24 can merge into
the item-1 inventory. Regenerate all derived files, or check for drift (exit 3
if stale), with `design/netlist.sh [--check]`; per file it runs

```bash
source sim/harness/common/env.sh
klt netlist <path>.sch -o <path>.spice --block --rcfile design/xschemrc \
  --pdk "$PDK" --pdk-root "$PDK_ROOT"          # add --check to verify
```

| Path | Kind | Regeneration |
|---|---|---|
| `design/bitcell/bitcell.sch` | source | hand-edited (xschem) |
| `design/bitcell/bitcell.sym` | source | hand-edited |
| `design/bitcell/bitcell.spice` | derived | `design/netlist.sh` |
| `design/column/precharge.sch` | source | hand-edited |
| `design/column/precharge.sym` | source | hand-edited |
| `design/column/precharge.spice` | derived | `design/netlist.sh` |
| `design/column/column_mux.sch` | source | hand-edited |
| `design/column/column_mux.sym` | source | hand-edited |
| `design/column/column_mux.spice` | derived | `design/netlist.sh` |
| `design/column/sense_amp.sch` | source | hand-edited |
| `design/column/sense_amp.sym` | source | hand-edited |
| `design/column/sense_amp.spice` | derived | `design/netlist.sh` |
| `design/column/write_driver.sch` | source | hand-edited |
| `design/column/write_driver.sym` | source | hand-edited |
| `design/column/write_driver.spice` | derived | `design/netlist.sh` |
| `design/column/column.sch` | source | hand-edited |
| `design/column/column.sym` | source | hand-edited |
| `design/column/column.spice` | derived | `design/netlist.sh` |

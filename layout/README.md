# layout

Bitcell layout for the SG13G2 6T SRAM (issue #27) and the macro layout generator
(issue #28), both T1 checklist item 2. Macro DRC, LVS and power delivery are #29-#31.

## Entry points

| What | Command |
|---|---|
| Regenerate the bitcell and the 2x2 tile | `uv run --with klayout python3 layout/bitcell/generate.py` |
| Regenerate, then DRC / extract / LVS / tests | `./layout/verify.sh` |
| Re-mint the evidence reports | `./layout/reports/generate.sh` |
| Generator tests | `cd layout/bitcell && uv run --with pytest --with klayout pytest test_bitcell.py` |

| Regenerate the macro GDS, socket descriptor | `uv run --with klayout python3 layout/sram_256x32/generate.py` |
| Re-mint the macro record, socket and LEF | `./layout/reports/generate-macro.sh` |

Friction filed: 2AMLogic/klayout-tools#4605 (`.include` path with a hyphen truncated in `klt lvs`; the tile reference is inlined as a workaround).

Committed outputs: `layout/bitcell/sg13g2_sram_bitcell_6t.gds` (cell
`sg13g2_sram_bitcell_6t`) and `layout/bitcell/sg13g2_sram_bitcell_tile2x2.gds`
(2x2 mirror-abutment tile). GDS sha256s, the generator command, the deck
content hash and the area record are in `layout/reports/bitcell-record.json`.

## What the cell is

Drawn from `design/bitcell/bitcell.spice`: four `sg13_lv_nmos` W = 0.30 µm /
L = 0.13 µm (pull-downs and access), two `sg13_lv_pmos` W = 0.15 µm /
L = 0.13 µm. Every geometry value is a named constant in `generate.py` citing
the SG13G2 rule it derives from; none is copied from the `gf180-sram` origin
or from the foundry `BITKIT_*` cells (`spec/bitcell-decision.md` item 6).
Layers: Activ, GatPoly, Cont, Metal1, pSD, NWell. No Metal2 and no
`SRAM.drawing`.

**Tie decision: ties are in-cell.** A full-width p-substrate tie (VSS) and
n-well tie (VDD) sit inside the cell, each inset 0.105 µm from its edge, with
the VSS/VDD Metal1 risers running to the edge. Mirror copies merge the risers
and the tie strips, so supplies are continuous along a row and a column
without a separate tap cell. The extraction and LVS netlist therefore need no
tap ports (the reference `bitcell.spice` is matched as it stands). The cost is
height; the shipped array uses an external `BITKIT_TAP` instead.

NWell and pSD extend past the pitch box (by their enclosure of the edge tie
strips) and overlap in mirrored neighbours. The pitch box is the `prBoundary`
(189/4) rectangle; `klt stats` on the whole stream reports the larger bounding
box. Area is quoted from the pitch box.

## Results (klt 0.8.1.dev738, deck `sg13g2` v0.8.0, hash `sha256:1c95db40…6dd15`)

| Check | Cell | 2x2 tile | Report |
|---|---|---|---|
| `klt drc --deck sg13g2` | clean, 0 violations | clean, 0 violations | `drc-bitcell.json`, `drc-tile2x2.json` |
| `klt extract` | 6 devices (4 nfet W 0.30 / 2 pfet W 0.15, all L 0.13), 7 pins | 24 devices | `extract-bitcell.json` |
| `klt lvs` vs `bitcell.spice` | match, 0 mismatches | match vs four `bitcell` instances (reference flattened, disclosed `topology.flattened` warning) | `lvs-bitcell.json`, `lvs-tile2x2.json` |

**Area**: 2.870 × 3.605 µm = 10.346 µm², **2.96×** the 3.50 µm² reference
(`BITKIT_CELL_SUB`, 1.76 × 1.99 µm). Recorded, not a requirement; the cell is
drawn to ordinary rules with margin, with in-cell ties and single-layer
Metal1 cross-coupling, and is not density-optimised.

### Coverage gaps (what "clean" does not mean)

- The curated deck enforces 62 rules. It carries no GatPoly end-cap (Gat.c),
  no Cont-on-GatPoly to Activ (Cnt.e), no Cont-to-gate (Cnt.f), no pSD
  enclosure or spacing to n+ Activ (pSD.c/d/e), and no Activ area rule. Those
  are met by construction from the PDK's `sg13g2_tech_default.json` values but
  are **not machine-checked here**.
- The PDK's native KLayout DRC (`run_drc.py`) requires KLayout >= 0.29.11;
  this host has 0.28.16 (and host tools are not changed), so the native deck
  was **not run**. Running it on both GDS files is the open follow-up.
- Layers 5/1 (GatPoly label), 8/25 (Metal1 text) and 189/4 (prBoundary) carry
  no rules. NW.b1 (net-aware well spacing) is reported unchecked by the engine.
- Unmodeled by the deck: LU.a, LU.c, LU.c1, LU.d, LU.d1, Pad.* (listed in the
  record).
- The DRC and LVS above say nothing about SRAM-specific behaviour (read
  stability, write margin); the cell is only checked for rule and netlist
  correctness. Q/QB labels are used in the single-cell run; the tile leaves
  them anonymous.

## `SRAM.drawing` (25/0)

The cell does not use the marker. See `layout/reports/sram-rule-survey.md`.

## Reports are append-only evidence

Files in `layout/reports/` are not edited to change a result. A re-run after a
layout or klt change is committed as a new result with the reason in the
commit message.

## Macro (`layout/sram_256x32/`, issue #28)

`generate.py` builds top cell `macro` (128 rows x 64 columns, mux 2; the directory
name follows the 256 x 32 capacity) from `design/macro/macro.spice`. Outputs:
`macro.gds`, `macro.socket.json` (the descriptor `klt lef-abstract` consumes) and
`macro.lef` (`--obs-mode coarse`, PDK `ihp-sg13g2`). Hashes, flattened counts,
area and the klt/deck identity are in `layout/reports/macro-record.json`.

- **Array**: the bitcell of `layout/bitcell/generate.py`, as cell `bitcell`
  (unlabelled; same geometry as `sg13g2_sram_bitcell_6t`). 8192 instances via
  `bl_pair` (128) x 64 columns in 32 `bit_slice`. Odd rows mirror in Y, odd
  columns in X. No edge or corner dummies: ties are in-cell.
- **Periphery**: every other subcircuit is a cell of the netlist's name made of real
  transistors at the netlist's W/L (Activ, GatPoly, Cont, Metal1, NWell, pSD), net
  names as Metal1 labels. Column-path cells sit under their bit-line pair at the
  slice pitch; the decoder, control and address latch sit left of the array; the
  data and output latches sit below the column path.
- **Pins**: 0.5 um Metal2 squares on the boundary (D/Q on the bottom edge, A, CEN,
  CLK, GWEN, WEN, VDD, VSS on the left), labelled on Metal2 text. `klt socket-check`
  passes; every LEF pin reports `geometry_source: drawn`.
- **Area**: 312.56 x 565.805 um = 176,848 um2, **3.57x** the shipped macro's
  49,488.5 um2 (recorded, no threshold). The bitcells alone are 84,757 um2.

### What this macro is not (read before citing it)

Issue #88 is landing in steps; this is the state after step 2 (supply rails, #92),
following step 1 (taps, #96). Every periphery transistor carries a body tie (n+
Activ in the PMOS well; p+ Activ in pSD for NMOS) and every tie, and every bitcell
VDD/VSS riser, is now wired to a VDD or VSS rail: Via1 and a Metal2 pad on each
tie, a Metal2 stub to a Metal3 lane (4 um pitch, VDD/VSS interleaved, one set per
floorplan region), and the lanes to two Metal4 trunks (VDD x = -2.3, VSS x = -1.1)
in the corridor left of the array; in the array a Metal1 pad and Via1 on the risers
and a Metal2 strap at every row seam (even VSS, odd VDD; the mirror abutment merges
the risers there) run to the same trunks through Via2, Metal3 and Via3. The
`VDD`/`VSS` **pin squares are not connected to the rails** (that is #95), and there
is still **no signal routing**: none in the periphery, none between the array and
the column path or decoder, no wordline routing, and the LEF signal pins connect to
nothing. Evidence (`layout/reports/macro-record-rails.json`, `./layout/verify.sh`
step 8): 2796 of 2796 periphery ties and 8192 + 8192 bitcell risers reach their own
rail, none the other, no VDD-VSS short in a flat Metal1-Metal4 connectivity
analysis, and `klt extract --deck sg13g2` now reports two bulk nets, VSS for all
34,118 nfet and VDD for all 17,830 pfet (before the rails every device had its own
bulk net). The nets are still not the netlist's signal nets, so the macro is not
LVS-able. The #87 (`macro-record.json`) and #96 (`macro-record-taps.json`) records
are unchanged. The Via1 sits directly over the tie Cont; the curated deck does not
test stacking and the PDK-native deck was not run. The D/Q pins moved 0.5 um outward
so periphery Metal2 keeps its spacing to them. Area 333.560 x 573.615 um =
191,335.0 um2, **3.87x** the reference. Rail widths carry no current or
electromigration analysis.

Known: the macro DRC (`klt drc --deck sg13g2`) reports `nwell.space.1` only, 522 on
the #87 layout and 563 with the taps (the 41 added are the same rule, in the packed
periphery) and still 563 with the rails (no Metal2-Metal4 or via rule fires); full
macro DRC is #29. Remaining for #88, in order: array-to-column-path and wordline
routing, periphery signal nets and pin connection. Unrun here: PDK-native DRC and `klt array-check`.

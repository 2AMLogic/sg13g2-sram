# layout

Bitcell layout for the SG13G2 6T SRAM (issue #27, T1 checklist item 2, bitcell
step). Array, periphery and macro views are #28 and later.

## Entry points

| What | Command |
|---|---|
| Regenerate the bitcell and the 2x2 tile | `uv run --with klayout python3 layout/bitcell/generate.py` |
| Regenerate, then DRC / extract / LVS / tests | `./layout/verify.sh` |
| Re-mint the evidence reports | `./layout/reports/generate.sh` |
| Generator tests | `cd layout/bitcell && uv run --with pytest --with klayout pytest test_bitcell.py` |

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

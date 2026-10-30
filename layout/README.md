# layout

Bitcell layout for the SG13G2 6T SRAM (issue #27) and the macro layout generator
(issue #28), both T1 checklist item 2. Macro DRC (#29) is in the section below; LVS and power delivery are #30-#31.

## Entry points

| What | Command |
|---|---|
| Regenerate the bitcell and the 2x2 tile | `uv run --with klayout python3 layout/bitcell/generate.py` |
| Regenerate, then DRC / extract / LVS / tests | `./layout/verify.sh` |
| Re-mint the evidence reports | `./layout/reports/generate.sh` |
| Generator tests | `cd layout/bitcell && uv run --with pytest --with klayout pytest test_bitcell.py` |

| Regenerate the macro GDS, socket descriptor | `uv run --with klayout python3 layout/sram_256x32/generate.py` |
| Re-mint the routed-macro record, socket and LEF (~2 min, runs `klt extract`) | `./layout/reports/generate-macro-routed.sh` |

`generate-macro.sh` minted the unrouted macro's `macro-record.json` (#28) and now refuses to overwrite it.

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
- **Area**: 314.59 x 561.855 um = 176,754 um2, **3.57x** the shipped macro's
  49,488.5 um2 (recorded, no threshold). The bitcells alone are 84,757 um2.

### Array-interface routing (issue #94, seam 3 of #88)

The wordlines and bit lines are now wired to the periphery; `layout/reports/macro-record-routed.json`
is the new record (`macro-record.json` is unchanged).

- **Wordlines** (128): GatPoly landing pad left of the array edge, Cont, Metal1, Via1, Metal2,
  Via2, Metal3 along the row, a private Metal2 lane per wire in the decoder-to-array gap,
  a private Metal3 track per wire above its decoder terminal row, and Via1 on the first
  `wl_driver` device on `WL` (its PMOS drain, `XMPD`).
- **Bit lines** (128): a Via1/Via2 stack on a Metal1 pad abutting the bottom of each stripe
  (the stripe is unchanged), a Metal3 lane at the stripe's x, and a Metal2 jog to one `BL`/`BLB`
  terminal of the precharge and of the column mux.
- Terminal coordinates come from the generator's placement record, every width/spacing/via size is
  a named constant citing its `klt deck rules` id, and all of it is Metal2/Metal3/Via1/Via2.
- **Area**: the 128 lanes at 0.42 um pitch widen the decoder-to-array gap from 3.0 to
  55.34 um: 364.9 x 565.805 um = 206,462 um2, **4.17x** the shipped macro (was 3.57x). Recorded,
  not a requirement.
- **Evidence** (array interface only; reference comparison is #30): the layout net trace in
  `test_macro.py` connects 128/128 wordlines (poly row to driver terminal) and 128/128 bit-line
  nets (stripe to both terminals), with no short among those 256 nets; `klt extract` agrees
  (128 wordline nets, each with 128 access gates; 128 bit-line nets carrying the macro,
  precharge and mux labels). `klt drc --deck sg13g2` reports no violation (the 522 `nwell.space.1` of
  the 0.5 um packing were cleared by `PACK_GAP` 0.65 um, #29). The tests delete one Via2 / Via1 and
  assert the trace then fails.

### What this macro is not (read before citing it)

It is **partly routed**. The array interface (wordlines, bit lines) is wired, and every
periphery transistor now carries a body tie (n+ Activ in the PMOS well; p+ Activ in pSD for NMOS)
with a Metal1 pad labelled with the netlist bulk net (#88 step 1, `macro-record-taps.json`). The
ties are **not wired to a rail**. There is still no signal wiring inside the periphery (a net
with several device terminals in one cell, such as `BL` on both precharge PMOS drains, is reached
at one of them) and none to the macro pins; no supply rails (#92). The LEF pins are drawn Metal2
but are not connected to the logic, so the macro is not LVS-able yet. The wordline label on
GatPoly text (5/1) sits mid-cell, off the poly row, and is not read by `klt extract`; the
wordline nets take their names from the driver labels. Routing the rest is #92 and #95; #29
(DRC), #30 (LVS) and #31 (power ERC) cannot proceed past them. Unrun here: the PDK-native DRC,
`klt array-check`, and DRC of the periphery against rules the curated deck lacks.

### Macro DRC (issue #29, T1 item 3)

`klt drc --deck sg13g2 --top macro layout/sram_256x32/macro.gds` ->
`layout/reports/drc-macro.json`: `status: clean`, `violation_count: 0`, deck
`sg13g2` hash `sha256:1c95db40596afc5412e216009bcf0b775d1d74895b32738447eccbc76336dd15`
(released), input hash `sha256:7135c537…b0edfb`, the **partly routed** macro (array interface
wordlines and bit lines on Metal2/Metal3/Via1/Via2, periphery body ties). **This is a clean DRC of what is
drawn**: periphery signal routing, supply rails and pin routing are not drawn (see above), so no rule
is exercised on them.

The first run was not clean: 522 `nwell.space.1` violations, the periphery packer
put PMOS wells 0.5 um apart against the 0.62 um minimum (NW.b). Fixed in the
generator (`PACK_GAP` 0.65 um); no rule was waived and the deck was not trimmed.
The GDS, LEF, socket, `macro-record-routed.json` and item 2 envelope were regenerated
(`macro-record.json`, the unrouted #28 record, is append-only and unchanged).
The routed array interface was added by #94 on `main`; re-running the DRC on it at 0.65 um is clean.

Coverage, quoted from the report's `coverage` block:

- `layers_in_stream_without_rules`: `5/1`, `8/25`, `10/25`, `189/4`
- `deck_scope`: `Act`, `Cnt`, `Gat`, `M1`, `M2`, `M3`, `M4`, `M5`, `MIM`, `NW`,
  `TM1`, `TM2`, `TV1`, `TV2`, `V1`, `V2`, `V3`, `V4`, `pSD`
- `rules_skipped` (38): `metal1.enclosing.via1.1`, `metal2.enclosing.via2.1`,
  `metal3.enclosing.via3.1`, `metal3/4/5.space.1`, `metal3/4/5.width.1`,
  `metal4.enclosing.via4.1`, `metal5.enclosing.mim.1`,
  `metal5.enclosing.topvia1.1`, `mim.enclosing.topvia1.1`,
  `nwell.enclosing.nactiv{,.dig,.hv}.1`, `nwell.space.nactiv{,.dig,.hv}.1`,
  `topmetal1.enclosing.topvia{1,2}.1`, `topmetal1.{space,width}.1`,
  `topmetal2.enclosing.topvia2.1`, `topmetal2.{space,width}.1`,
  `topvia{1,2}.{space,width}.1`, `via{1,2,3,4}.{space,width}.1`. The full list is
  in the report.

Unchecked as a result: all rules on Metal2 and above and on every via layer, the
NWell-to-N+ Activ rules, and every density, antenna and latch-up rule (the deck
carries none). Periphery devices use bitcell-derived rule constants.

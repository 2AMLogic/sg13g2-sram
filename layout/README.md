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

`layout/reports/generate-macro.sh` minted the unrouted macro's `macro-record.json` (#28) and `macro-record-taps.json`, and was removed once it could only refuse to overwrite them. Both records still name it as `record_command`; recover the script with `git show cbf61db:layout/reports/generate-macro.sh`.

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

It is **partly routed**. The array interface (wordlines, bit lines) is wired; every
periphery transistor carries a body tie (n+ Activ in the PMOS well; p+ Activ in pSD for NMOS)
with a Metal1 pad labelled with the netlist bulk net (#88 step 1, `macro-record-taps.json`); and
every tie and every bitcell VDD/VSS riser reaches a VDD or VSS rail (#88 step 2, #92, re-planned
in #102; `macro-record-rails.json`). The `VDD`/`VSS` pin squares are **not connected to the
rails** and there is still no signal wiring inside the periphery (a net with several device
terminals in one cell, such as `BL` on both precharge PMOS drains, is reached at one of them)
and none to the macro pins. The LEF pins are drawn Metal2 but are not connected to the logic, so
the macro is not LVS-able yet. The wordline label on GatPoly text (5/1) sits mid-cell, off the
poly row, and is not read by `klt extract`; the wordline nets take their names from the driver
labels. Routing the rest is #95; #30 (LVS) and #31 (power ERC) cannot proceed past it. Unrun
here: the PDK-native DRC, `klt array-check`, and DRC of the periphery against rules the curated
deck lacks.

#### Supply rails (issue #92, re-planned in #102)

The decoder-to-array gap is the 55.34 um wordline fan-out (`WL_FANOUT_GAP`): 128 Metal2 lanes
at `LANE_PITCH` 0.42 um and the Metal3 runs at each wordline y. The rails therefore do not use
it, and `RAIL_LANE_PITCH` (4 um, the rail lane pitch) is named apart from `LANE_PITCH`.

- **Periphery ties**: Via1 and a Metal2 pad on each tie; a Metal2 stub (placed clear of the
  signal Metal2 and of the tie pads, read from the layout) to a Via2/Metal3 pad/Via3 landing on a
  **Metal4 lane** (4 um pitch, VDD/VSS interleaved, one set per floorplan region). The Metal3 pad
  is the only Metal3 a rail adds, and it is placed 0.21 um clear of the signal Metal3.
- **Trunks**: two Metal5 stripes right of the array (VSS inner, VDD outer). Lanes reach them
  through Via4; the lanes cross the wordline gap on Metal4 only.
- **Array**: Metal1 pad and Via1 on the risers, a Metal2 strap at every row seam (even VSS, odd
  VDD; the mirror abutment merges the risers there) that continues right of the array to its
  trunk through Via2/Metal3/Via3/Metal4/Via4. Seam 0 sits on the bit-line Via1/Via2 stacks below
  the array, so it is a pad per column plus a Metal4 strap instead of a full-width Metal2 strap.
- **Interaction with the routing**: the tie Metal2 pads are obstacles for the bit-line jogs and
  the wordline terminal stubs (a stub jogs right when a pad sits beside it); without that, 231
  periphery ties had a bit-line Metal2 wire through their pad.
- **Check** (`rails_check.py`, `test_macro.py`, `./layout/verify.sh` step 9): 2796 of 2796 ties and
  8192 + 8192 risers on their own rail, none on the other, no VDD-VSS short in a flat
  Metal1-Metal5 connectivity analysis; zero rail shapes on Metal1-Metal3 or Via1-Via3 inside the
  wordline gap (a test inserts one Via2 and asserts the check then fires); the 128 wordline and
  128 bit-line nets stay distinct. `klt drc --deck sg13g2` is clean with Metal4/Metal5/Via3/Via4
  rules now checked (they had no geometry before).
- **Not covered**: no current or electromigration analysis of the rail widths; the Via1 sits
  directly over the tie Cont and the curated deck does not test stacking; extraction-level
  netlist comparison is #30. Area 417.960 x 588.365 um = 245,913.0 um2, **4.97x** the reference
  (trunks widen x by 3.08 um; the D/Q pins sit 0.5 um outside the content).

### Macro DRC (issue #29, T1 item 3)

`klt drc --deck sg13g2 --top macro layout/sram_256x32/macro.gds` ->
`layout/reports/drc-macro.json`: `status: clean`, `violation_count: 0`, deck
`sg13g2` hash `sha256:1c95db40596afc5412e216009bcf0b775d1d74895b32738447eccbc76336dd15`
(released), input hash `sha256:76b3a60b…86715e`, the **partly routed** macro (array interface
wordlines and bit lines on Metal2/Metal3/Via1/Via2, periphery body ties, supply rails on
Metal4/Metal5/Via3/Via4 as well). **This is a clean DRC of what is drawn**: periphery signal
routing and pin routing are not drawn (see above), so no rule is exercised on them.

The first run was not clean: 522 `nwell.space.1` violations, the periphery packer
put PMOS wells 0.5 um apart against the 0.62 um minimum (NW.b). Fixed in the
generator (`PACK_GAP` 0.65 um); no rule was waived and the deck was not trimmed.
The GDS, LEF, socket, `macro-record-routed.json` and item 2 envelope were regenerated
(`macro-record.json`, the unrouted #28 record, is append-only and unchanged).
The routed array interface was added by #94 on `main`; re-running the DRC on it at 0.65 um is clean.
The supply rails (#102) were first drawn with four `metal2.width.1` violations (a stub overlapping
its tie pad by 0.045 um left a sliver); the stub now keeps `M2.b` clear of its own pad or merges with
it, and the rerun is clean. `macro-record-routed.json` records the macro before the rails and is not rewritten.

Coverage, quoted from the report's `coverage` block:

- `layers_in_stream_without_rules`: `5/1`, `8/25`, `10/25`, `67/25`, `189/4`
- `deck_scope`: `Act`, `Cnt`, `Gat`, `M1`, `M2`, `M3`, `M4`, `M5`, `MIM`, `NW`,
  `TM1`, `TM2`, `TV1`, `TV2`, `V1`, `V2`, `V3`, `V4`, `pSD`
- `rules_skipped` (20, all `no_applicable_geometry` under `inapplicable`):
  `metal5.enclosing.mim.1`, `metal5.enclosing.topvia1.1`, `mim.enclosing.topvia1.1`,
  `nwell.enclosing.nactiv.1`, `nwell.enclosing.nactiv.dig.1`,
  `nwell.enclosing.nactiv.hv.1`, `nwell.space.nactiv.1`, `nwell.space.nactiv.dig.1`,
  `nwell.space.nactiv.hv.1`, `topmetal1.enclosing.topvia1.1`,
  `topmetal1.enclosing.topvia2.1`, `topmetal1.space.1`, `topmetal1.width.1`,
  `topmetal2.enclosing.topvia2.1`, `topmetal2.space.1`, `topmetal2.width.1`,
  `topvia1.space.1`, `topvia1.width.1`, `topvia2.space.1`, `topvia2.width.1`.

The other 42 rules were checked (`rules_checked`), including Metal1-Metal5
width/space, Via1-Via4 width/space, Via/Metal enclosure up to Via4 and the NWell-to-P+ Activ
rules. Unchecked as a result: TopMetal1/2, MIM, TopVia1/2, the NWell-to-N+ Activ rules (no
geometry), and every density, antenna and latch-up rule (the deck carries none; `unmodeled_rules`
lists LU.* and Pad.*). Periphery devices use bitcell-derived rule constants.

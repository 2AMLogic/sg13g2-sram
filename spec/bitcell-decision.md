# Decision record: the bitcell question

**Status**: Proposed, 2026-10-17 (not self-ratified; ratification is an
operator step)
**Resolves**: #2, "First question, before the spec"
**Origin**: `gf180-sram` `spec/bitcell-decision.md` @ `d0bacc0`

## Question

Does SG13G2 ship a usable 6T bitcell as a standalone, tileable primitive, or
only embedded inside the shipped `sg13g2_sram` macros?

## Answer

**Embedded only, but more exposed than on gf180mcu. There is no standalone
primitive library (no per-cell LEF, no per-cell CDL file, no cell
library separate from the macros), yet the 6T cell is a distinct,
named, hierarchical cell in every macro's CDL and GDS, with a stated SRAM
marker layer (`SRAM.drawing`, 25/0) in the PDK layer map.** Verdict:
**draw our own bitcell and array** (the origin's Option 2), using the
shipped cell as the sizing and topology reference. The shipped GDS cell is
not a tileable primitive this repo can instantiate as a deliverable: it is
foundry macro content generated per macro, with macro-specific names, and
this repo must generate its own views (see `spec/sram.md`, Deliverables).

## Evidence

All inspected 2026-10-17 in the PDK checkout `~/share/pdk/ihp-sg13g2`,
library `libs.ref/sg13g2_sram/` (`cdl gds lef lib verilog doc` views; 27
macros, 1-port and 2-port). Reference instance:
`RM_IHPSG13_1P_256x32_c2_bm_bist`. The checkout is not a git tree; `klt pdk find`
reports it as `ihp-sg13g2`, version stamp `fetched:0.3.0`. Pinning the PDK
is #5's job.

1. **The cell is a distinct CDL subcircuit.**
   `cdl/RM_IHPSG13_1P_256x32_c2_bm_bist.cdl` defines
   `RM_IHPSG13_256x32_c2_1P_BITKIT_CELL` with ports
   `BLC_BOT BLC_TOP BLT_BOT BLT_TOP LWL NW PW RWL VDD VSS` and six
   transistors: two `sg13_lv_nmos` pull-downs (`MN0`, `MN1`), two
   `sg13_lv_pmos` pull-ups (`MP0`, `MP1`) and two `sg13_lv_nmos` access
   devices (`MN2`, `MN3`). Sizes: NMOS `w=300n l=130n`, PMOS `w=150n l=130n`.
   So pull-down : access ratio is 1 : 1 (beta ratio 1.0) and the pull-up is
   half the NMOS width. That is the sizing reference, and it is an unusual
   point (a beta ratio of 1 leaves read stability to the process and to
   the macro's read scheme). Three `lvsres` resistors tie the bitline
   top/bottom halves and the two wordline halves (`LWL`/`RWL`) together
   electrically; these are layout-stitching artifacts of the foundry cell,
   not circuit elements.
2. **The CDL also carries array scaffolding as separate cells**:
   `…BITKIT_CORNER`, `…BITKIT_EDGE_LR` (wordline-edge dummies),
   `…BITKIT_EDGE_TB` (bitline-edge cells), and `…BITKIT_16x2_SRAM`, a
   16 row × 2 column tile (32 `BITKIT_CELL` instances). The macro is built
   from this tile, so the foundry flow itself tiles a cell with explicit
   edge, corner and tap cells. Our own array needs the same scaffolding.
3. **The GDS carries the same hierarchy.**
   `gds/RM_IHPSG13_1P_256x32_c2_bm_bist.gds` has 135 cells, including
   `RM_IHPSG13_1P_BITKIT_CELL`, `…_CELL_SUB`, `…_CELL_2x1`, `…_TAP`,
   `…_16x2_SRAM`, `…_16x2_EDGE_TB`, `…_16x2_EDGE_LR`, `…_16x2_CORNER`,
   `…_16x2_POWER_ramblk`. Measured with KLayout: `BITKIT_CELL_SUB` is
   1.76 × 1.99 µm (3.50 µm² per bit); the 16×2 tile is 5.92 × 18.92 µm
   (3.50 µm² per bit, including no edge cells). `BITKIT_CELL` itself is
   3.11 × 1.99 µm because its bounding box includes the wordline/bitline
   stitching geometry, so per-bit area is taken from the tile, not from
   that box. The cell layers include `SRAM.drawing` (25/0), `Activ`,
   `GatPoly`, `NWell`, `pSD`, `Cont`, `Metal1`–`Metal3` and `Via1`–`Via2`.
4. **The LEF exposes none of it.** `lef/…256x32_c2_bm_bist.lef` is
   `CLASS BLOCK`, 416.64 × 118.78 µm, with signal and power pins and
   metal obstructions on Metal2 and Metal4; there is no mention of
   `BITKIT` (`grep -c -i bitkit` = 0). The bitcell has no abstract. The
   only way to see it is the CDL or the GDS.
5. **There is no standalone library of cells.** The `sg13g2_sram` library
   directory holds macros only. The cells are named per macro
   (`RM_IHPSG13_256x32_c2_1P_…` in CDL, `RM_IHPSG13_1P_…` in GDS) and are
   regenerated per instance. Nothing in the PDK offers the cell as a
   standalone, versioned, tileable primitive.
6. **Reuse terms**: the macro CDL, LEF and datasheet carry the Apache-2.0
   header "Copyright 2025 IHP PDK Authors". Studying and citing the cell is
   permitted. Copying its geometry into this repo's layout would be
   redistribution of foundry macro content; we draw our own.
7. **Reference macro numbers**: see `spec/sram.md`, "Reference row".

Not established (recorded as open, verify at first run):

- Whether the SG13G2 DRC deck relaxes rules inside the `SRAM.drawing`
  marker, as gf180mcu's `SramCore` does. The marker exists in the PDK layer
  map; its rule scope is not read yet. Owner: the bitcell layout issue.
  Our custom cell claims no relaxation until a rule survey says what the
  marker permits (the origin did this survey at `layout/reports/sram-rule-survey.md`).
- Well and substrate strap spacing in the shipped array (the `BITKIT_TAP`
  cell is 3.225 × 0.785 µm). Needed for the latch-up rule check.

## Scope decision

Two options, as in the origin:

1. Integrate a shipped macro. Rejected: this repo's purpose is array
   generation, macro-level LVS and LEF/Liberty generation (`CLAUDE.md`,
   "The array is the point").
2. **Draw a custom bitcell and array**, using the shipped cell's topology
   and sizing as the reference. **Chosen.**

### Consequence for sizing (so downstream issues are unblocked)

- The cell is 6T on `sg13_lv_nmos` / `sg13_lv_pmos` (1.2 V devices), minimum
  length 130 nm.
- Starting sizing for the bitcell characterization issue: pull-down
  `W/L = 300n/130n`, pull-up `150n/130n`, access `300n/130n` as the
  *reference point*, then sweep access width and pull-down width against
  read SNM and write margin at the corner set in `spec/sram.md`. The
  beta ratio must be a result of that sweep, not an assumption: a ratio
  of 1.0 is what the foundry shipped, not proof it is stable at every
  corner under our read scheme.
- Area comparison target: 3.50 µm² per bit for the shipped cell. Our cell
  is expected to be larger (the origin's cell was 1.35× its foundry
  reference); the ratio will be recorded, not required.

## Tool notes

- `klt pdk cells --pdk ihp-sg13g2` (klt 0.7.1.dev1743+g7ee09483b748, PDK
  version stamp `fetched:0.3.0`) lists only `sg13g2_stdcell`; the
  `sg13g2_sram` hard-macro library is not enumerated, the same class of
  gap the origin hit. Filed generically as
  [2AMLogic/klayout-tools#3806](https://github.com/2AMLogic/klayout-tools/issues/3806),
  together with the variant-name mismatch (`--pdk sg13g2` does not resolve;
  `ihp-sg13g2` does). Until fixed, the library is inspected by direct reads.
- Cell geometry was read with `klayout -b` and the standard `pya` API.

## References

- `~/share/pdk/ihp-sg13g2/libs.ref/sg13g2_sram/{cdl,gds,lef,doc}/RM_IHPSG13_1P_256x32_c2_bm_bist.*`
- `~/share/pdk/ihp-sg13g2/libs.tech/klayout/tech/sg13g2.lyp` (`SRAM.drawing`
  = 25/0)
- `gf180-sram` `spec/bitcell-decision.md` @ `d0bacc0`

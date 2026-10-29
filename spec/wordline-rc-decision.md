# Decision record: physical row/column organization and a wire-RC check on the wordline and bit lines

**Status**: Proposed, 2026-10-29 (not self-ratified). Ratification is the
operator's approval of the PR that lands this file, as for the sibling
records. Nothing here is a result.
**Resolves**: #70 (finding F3 of the EE-key review on #37)
**Depends on**: `spec/sram.md`, `spec/write-pulse-width-decision.md`
**Origin**: `gf180-sram` `spec/wordline-rc-decision.md` @ `68654da` (rule
and structure inherited; every number re-derived or left open)
**Amends**: nothing. `spec/sram.md` gains two Open-items rows and a pointer
on the Organization row; no row's value changes and it stays Proposed.

## Question

`spec/sram.md` states "256 words × 32 bits, fixed" and no physical row/column
split. It has no row or open item for wordline or bit-line RC, and its
45-corner set (5 × 3 × 3) has no interconnect axis. The origin found late that
wordline RC decided whether a fixed write pulse reached the far cell, and had
to re-floorplan. What physical organization is proposed here, and what must be
checked on extracted wire RC before any timing result is claimed?

## This is a comparison, not a qualification

This record reads the origin and the PDK's text files. **No SPICE, extraction
or layout was run**, and no RC number below is a result of this repo. Every
organization named here is a candidate, not a fact.

## What the origin found (read, not reproduced)

`gf180-sram` `spec/wordline-rc-decision.md` @ `68654da`, section "What the
single-corner comparison shows" (180 nm, 3.3 V, 2 ns pulse):

- A left-fed 128-cell Poly2 row (571 µm, 256 access gates) at one corner
  (`ss_125c_2.97v`): driver output reaches 50 % at 0.21 ns, the **far end
  reaches 50 % at 1.57 ns**, against a 2 ns write-pulse floor. With Poly2 R
  ×1.5 the far end never reaches 50 % on a 2 ns pulse.
- The origin's own caveats carry over: one corner and one bench; the criteria
  were the drafting agent's; a crossing time is not a write margin; the cell
  flip time with an ideal wordline (85 ps) is not proof of margin.
- The origin's resolution was a centre-fed row, and its pass criterion was
  that the far-cell wordline waveform meet the **already ratified**
  write-margin requirement at every corner, evaluated at the PDK's stated
  high-end poly sheet resistance. No new threshold was invented. That is the
  rule inherited here.

## What is known here

1. **Organization is not recorded.** `spec/sram.md` (Organization row) says
   256 × 32 only. Its Reference row records the shipped macro as "256 words ×
   32 bits, column mux 2" (datasheet). Column mux 2 over 32 bits implies
   64 columns per word-line group and 256 / 2 = 128 rows: **128 rows × 64
   columns** (derived from that datasheet row, not read from the shipped
   layout).
2. **The pulse has less slack than the origin's.** `spec/write-pulse-width-decision.md`
   proposes 1 ns (the origin used 2 ns). That value is proposed and
   unconfirmed (#69), so the same wordline-delay risk applies with a shorter
   window.
3. **Wire RC is "Not established"** (`sim/array/README.md`, line 35). No
   extracted array layout exists; the bitcell layout is #27.
4. **What the PDK states** (files named; none was simulated):

   | Quantity | Value | Source |
   |---|---|---|
   | `GatPoly` sheet resistance, typical | 7.0 Ω/sq | `libs.tech/parasitics/itf/sg13g2_typ.itf` (`RPSQ=7.0`) |
   | `Metal1` sheet resistance, typical / high-end | 0.110 / 0.135 Ω/sq | ITF (`RPSQ=0.110`); `libs.tech/magic/ihp-sg13g2-extract.tech` (`resist (allm1)/metal1 110` and, under "High-end corner resistances", `135`) |
   | `Metal2`–`Metal5` sheet resistance, typical / high-end | 0.088 / 0.103 Ω/sq | same two files |
   | Contact (`Cont`) per via, typical / high-end | 15 Ω / 20 Ω | ITF (`RPV=15.0`); extract tech (`contact pc 15000` / `20000`) |
   | Dielectric stack (ER, thickness) | one typical stack | ITF, `DIELECTRIC` lines |
   | `rsil` (silicided poly resistor device) sheet resistance, best / typ / worst | 6.02 / 7.0 / 7.98 Ω/sq | `libs.tech/ngspice/models/cornerRES.lib` (`res_bcs`, `res_typ`, `res_wcs`) |

   **Not found:** a stated *high-end* `GatPoly` interconnect sheet
   resistance. The high-end table in `ihp-sg13g2-extract.tech` lists metals
   and contacts but no poly interconnect line, and the ITF is typical only.
   The `rsil` 7.98 Ω/sq is a *device* corner for a resistor, not an
   interconnect bound, so it is cited as the nearest PDK-stated poly figure
   and is not asserted to be the interconnect high end. **Not found:** a
   stated interconnect-capacitance corner. `cornerCAP.lib`'s `cap_cpara`
   (0.9 / 1.0 / 1.1) scales capacitor *devices*, not wire capacitance. Which
   layer the wordline actually runs on in the repo's own array is decided by
   the array layout issue; `spec/bitcell-decision.md` lists `GatPoly` and
   `Metal1`–`Metal3` in the foundry cell.

## Options, best to worst for this block

**A. 128 rows × 64 columns (column mux 2), as the shipped macro.** Proposed
candidate. Shortest wordline (64 cells) of the options that keep the
shipped macro's organization, which is the comparison point; the longer bit
line (128 cells) is what must then be checked. Derived in "What is known"
item 1; not a fact until the array layout exists.

**B. 64 rows × 128 columns (column mux 4), the origin's organization.**
Halves the bit-line length and doubles the wordline to 128 cells, which is
exactly the left-fed row the origin found marginal at 2 ns. Not preferred:
it starts from the risk the origin hit, with a shorter pulse.

**C. 256 rows × 32 columns (no mux).** Shortest wordline, longest bit
line; every read then has the bit-line RC and capacitance of a 256-cell
column. Not preferred: moves the problem to the bit line and departs from the
comparison macro.

**D. Any of the above with the wordline fed from the centre or strapped in
metal.** A mitigation, not an organization. Which feed is used is decided by
the array layout issue after the check below shows whether it is needed; the
origin's centre-fed result is a reference, not a precedent for this PDK.

The organization is chosen by the check below on extracted RC, not by this
record. Choosing A now only fixes the starting point the check is run on.

## Required: a wire-RC check before any timing claim

Before any write-margin, access-time or Liberty timing result is claimed, the
wordline and bit-line RC of the chosen organization must be extracted from its
layout and simulated with the far-cell waveform in place of an ideal
wordline. This record does not run it.

### Interconnect-RC axis for the corner set

The corner set in `spec/sram.md` gains a **required interconnect axis**
(proposed here; it enters the table only if this record is ratified and a
later change to `spec/sram.md` names it):

| Case | Resistance | Capacitance |
|---|---|---|
| Typical | the ITF typical values above | the ITF stack as given |
| High-end R | the PDK-stated high-end values above (Metal1 0.135, Metal2–5 0.103 Ω/sq, `Cont` 20 Ω) and, for poly, the highest PDK-stated poly sheet resistance found at that time; if none is found the record of the run says so | not scaled: no PDK-stated capacitance corner was found |

Rules for the axis: only values stated by a named PDK file are used; **no
multiplier such as ×1.5 is invented** (the origin's ×1.5 was a sensitivity
assumption, and its record replaced it with the PDK's stated value); and the
source file is named in every run's record. Whether the interconnect axis
multiplies the 45 corners or is run on the worst few is a later decision
record's to make with evidence; this record does not prune the matrix.

### Pass criterion

Reused, not new: the far cell, driven by the extracted wordline waveform,
meets the ratified write-margin requirement of `spec/sram.md` ("Write
margin": strictly positive at every corner, within the fixed write pulse of
`spec/write-pulse-width-decision.md`), plus the existing read SNM and hold SNM
requirements. **No threshold is introduced**, and no numeric wordline delay
limit is ratified by this record.

## Later validation matrix (proposal only; none of it is run or authorized by this PR)

1. Fix the organization from the array layout (#27 and the array issue);
   record it in `spec/sram.md` by a decision record.
2. Extract wordline and bit-line RC for the actual array, naming the
   extractor and the pin or drive node of each bench (the origin's
   mid-ladder-pin pitfall is a reason to name it).
3. Run the far-cell write-margin recheck over the corner set with the
   interconnect axis above, on the batch fleet.
4. Check bit-line RC against the read path: sense timing with wire RC in the
   path, not a sum of separate benches.
5. If the check fails, take the mitigation (centre feed, metal strap, or a
   different organization) by decision record. Do not relax the pulse or the
   margin to pass.

## What this record does not do

Run any SPICE, extraction or layout; confirm the 1 ns pulse (#69); define
write margin more tightly (#71); add Monte Carlo (#68); fix the wider
Open-items inconsistencies (#72); change any value in `spec/sram.md`; or
qualify any organization.

## References

- `gf180-sram` `spec/wordline-rc-decision.md` @ `68654da`
  (`~/GitHub/gf180-sram`).
- `spec/sram.md` (Organization, Reference, Corner set, Open items),
  `spec/write-pulse-width-decision.md`, `spec/bitcell-decision.md`,
  `sim/array/README.md`.
- PDK files under `~/share/pdk/ihp-sg13g2/libs.tech/`:
  `parasitics/itf/sg13g2_typ.itf`, `magic/ihp-sg13g2-extract.tech`,
  `ngspice/models/cornerRES.lib`, `ngspice/models/cornerCAP.lib`.

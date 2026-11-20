# bitcell characterization

Hold SNM, read SNM and write margin of the 6T cell in `design/bitcell/` at the
reference sizing, over the spec's 45 corners (`spec/sram.md`, Corner set).
Every number here is **simulated** (ngspice + PSP103 through OSDI), schematic
level: no parasitics, no Monte Carlo, no array -- the post-layout
(schematic-vs-extracted) re-run is the last section of this file.

```bash
sim/bitcell/run_bitcell.sh     # new record under records/<UTC>/, never overwritten
sim/bitcell/run_pex.sh         # post-layout re-run (klt pex), same record convention
python3 sim/bitcell/test_bitcell_post.py
python3 sim/bitcell/test_measure_pex.py
```

- `bench_snm.cir` + `request_snm.json`: DC butterfly, hold (WL low) and read (WL
  and both bit lines at VDD). The storage loop is broken by forcing one storage
  node of a full cell (instance a: force Q, read QB; instance b: force QB, read
  Q), so no device is duplicated outside the schematic. The sweep is normalised
  (0..1 x VDD) so it follows the supply corner.
- `bench_write.cir` + `request_write.json`: 33 cells, bit-line low level 0 to
  0.8 V in 25 mV steps, BLB at VDD, one 1 ns wordline pulse
  (`spec/write-pulse-width-decision.md`). A cell flipped if Q < QB at the end of
  the pulse and still at 2.5 ns. **Write margin = highest bit-line low level
  that still flips**, so it is positive when the bit line need not reach 0 V,
  with 25 mV resolution (a quantisation, not a measurement noise floor). If the
  cell does not flip with BL at 0 V the margin is recorded as null (not positive).
- `bitcell_post.py`: SNM extraction and write-margin reduction.
- Negative control (typical point): pull-downs 150 nm and access 600 nm
  (beta 0.25). The script exits non-zero unless its read SNM drops below the
  reference cell's.

## SNM definition

SNM is the side of the largest square inscribed in a butterfly eye (Seevinck),
the minimum over the two eyes, computed exactly on the sampled polylines (the
same construction as `klt sim`'s native `snm` measurement, which the fleet
runner does not support yet, so it runs here). `sim/lib/common/snm_extract.py`
is run on the same curves and its value is kept as `*_snm_vgap_v`: it measures
the maximum **vertical** gap between the curves, which over-reads the square
(by 10-50% on these curves, e.g. typical hold 0.562 V vs 0.486 V). The recorded
margin is the square. A cell with no eye falls back to `snm_extract.py`'s signed
bistability deficit (<= 0), so a failing corner is counted, not dropped.

## Backend

Every run goes to the batch fleet, including the typical point, because this
host's ngspice (42) cannot load the OSDI v0.4 models (`sim/README.md`: ngspice >=
43 is needed). A failed submit exits non-zero; nothing falls back to a local
loop. The fleet runner is klt 0.7.0, which lacks `snm` and `initial_conditions`;
the benches avoid both (`.ic` cards, waveforms post-processed here).

## Results (first record, `records/20261023T231238Z/`)

Reference sizing, PDK v0.3.0, batch fleet runner klt 0.7.0 / ngspice 42 + OSDI.

| | Typical (mos_tt, 1.20 V, 27 C) | Worst of 45 corners |
|---|---|---|
| Hold SNM | 0.486 V | 0.390 V (mos_ff, 1.08 V, 125 C) |
| Read SNM | 0.213 V | 0.143 V (mos_fs, 1.08 V, 125 C) |
| Write margin | 0.400 V | 0.250 V (mos_sf, 1.08 V, -40 C) |
| Negative control read SNM | 0.131 V (< 0.213, detected) | |

All three are strictly positive at all 45 corners, at the reference sizing.
This is a deterministic, schematic-level result; the spec's Monte Carlo evidence
and the write-pulse flip-time check at `mos_ss`/1.08 V/125 C
(`spec/write-pulse-width-decision.md`, open items) are **not** done here, nor
the 0.5/1/2 ns sensitivity sweep, nor the rail-sharing decision.
`record.json` holds the summary, `grid_*.json`/`typical_*.json` every corner,
`curves/` the extracted voltage-transfer curves, `reports/` the `klt sim`
reports.

## Post-layout re-run (`klt pex`, issue #228)

The same three margins, schematic leg vs parasitic-extracted leg, on the
LVS-matched bitcell layout `layout/bitcell/sg13g2_sram_bitcell_6t.gds`:

```bash
sim/bitcell/run_pex.sh        # new record under records/<UTC>/, never overwritten
python3 sim/bitcell/test_measure_pex.py
```

- `klt pex --deck sg13g2 --pdk ihp-sg13g2 --backend batch --measure-command`:
  extraction is `klt pex`'s own (lumped star R per net, C to the deck's
  substrate net `vsubs`, deck-default parasitic settings); each leg is measured
  by `measure_pex.py`, which stages the benches above around whichever netlist
  the leg is handed and reduces with `bitcell_post.py` (SNM is not a `.meas`
  row, so the testbench mode cannot drive it). `pex_reference.spice` is the
  pin-order adapter (the extraction's top is
  `sg13g2_sram_bitcell_6t BL BLB Q QB VDD VSS WL`; the schematic declares
  `bitcell BL BLB WL VDD VSS Q QB`); both legs run byte-identical bench text.
- Corners: the one bounding each margin in the 45-corner schematic grid plus
  the typical point (`mos_fs`/1.08 V/125 C read, `mos_sf`/1.08 V/-40 C write,
  `mos_ff`/1.08 V/125 C hold, `mos_tt`/1.20 V/27 C): 12 delta rows, all `pass`.
- Batch fleet only; job ids are in the record. `layout/verify.sh` step 11
  re-runs the PDK-free extraction and checks its digest against the record.

Results (record `records/20261120T230551Z/`, envelope status `pass`, 12 rows,
0 failed, 0 errored; the run was minted twice against the fleet -- the first
envelope carried an absolute harness path in `measurement.command` and was
discarded before commit in favour of the repo-relative argv fix in
`run_pex.sh` -- and every value reproduced bit for bit across the two mints):

| Corner | hold SNM sch → ext | read SNM sch → ext | write margin sch → ext |
|---|---|---|---|
| mos_fs, 1.08 V, 125 C | 0.403574 → 0.403574 V (-0.000%) | 0.142974 → 0.142979 V (+0.004%) | 0.425 → 0.425 V (0%) |
| mos_sf, 1.08 V, -40 C | 0.460866 → 0.460866 V (-0.000%) | 0.246153 → 0.246155 V (+0.001%) | 0.250 → 0.250 V (0%) |
| mos_ff, 1.08 V, 125 C | 0.389837 → 0.389836 V (-0.000%) | 0.153844 → 0.153849 V (+0.003%) | 0.400 → 0.400 V (0%) |
| mos_tt, 1.20 V, 27 C | 0.485833 → 0.485833 V (-0.000%) | 0.213170 → 0.213177 V (+0.003%) | 0.400 → 0.400 V (0%) |

The schematic leg reproduces `records/20261028T143337Z` exactly (0.0 V
difference on all three margins at the typical point) -- the strongest
pin-order check available: a swapped pin collapses read SNM, it does not
perturb it by microvolts.

Extraction disclosures, quoted from the envelope: `body_bias.status` is
**`biased`** (`unbiased_device_count: 0`) -- the in-cell tie decision of
`layout/README.md` holds in the extracted netlist. `model_mismatch` is
**`null`**: the PDK-bound extraction instantiates the same
`sg13_lv_nmos`/`sg13_lv_pmos` device cards as the schematic (the PDK-free
deck binds generic `nfet`/`pfet` classes instead and reports
`model_mismatch.kind: model_set`, which is why the measured run is PDK-bound).
`extraction.model` is, verbatim:

- capacitance: "net-to-ground for every net's own (non-coupled) area/perimeter, plus net-to-net for the vertical-overlap coupling `coupling` describes below -- a coupled net pair gets a direct capacitor between their two hub nodes, not just capacitors to the deck's ground/substrate net"
- coupling: "vertical overlap (crossover) unconditionally -- where one net's conductor on an adjacent metal level sits directly over another *distinct* net's conductor, that overlap area is charged between the two nets instead of to ground (issue #760) -- plus lateral (same-layer, sidewall) coupling, but only for a net pair naming one of the caller's declared `--critical-net` nets (issue #976): facing-edge length within that layer's own minimum-spacing lookback is charged between the two nets, *additively* (not deducted from either net's substrate fringe term, unlike the vertical case -- a known simplification). Any same-layer pair with neither side named `--critical-net`, and fringe shielding in general, are still not modelled"
- resistance: "single lumped series resistance per net, distributed as a star across that net's device terminals (issue #592) -- not a per-segment, distributed RC ladder, *unless* `--distributed-rc` names this net via `--critical-net` (issue #977, Epic #709 Phase 2b): then the net's terminals are ordered along their approximate physical spread and its total R/C is broken into a chain of per-segment resistors (segment length proportional to inter-terminal distance) with a ground capacitor at each terminal node (proportional to its adjacent segment length/2), instead of one star hub -- still an approximation (terminal position is a device-placement proxy, not true per-segment routing geometry), but a strictly finer-grained one than the single-hub star"
- frequency: "quasi-static -- one frequency-independent R and C per net; no skin effect, no distributed transmission-line behavior"

**Why the deltas are this small.** Every net gained only its lumped star
resistance and one C to `vsubs` (per net, from the record): BL/BLB 1.983 Ω
(one terminal) + 0.326 fF, Q/QB 1.519 Ω over five terminals (0.21-0.36 Ω
each) + 0.233 fF, VDD 0.641 Ω over four + 0.116 fF, VSS 0.715 Ω over six +
0.128 fF; no net-to-net coupling capacitor was extracted (no `--critical-net`
was declared and no distinct-net vertical overlap was charged). The SNM rows
are DC operating points, where only the R drops shift the solve -- at the
bench's microamp-range cell currents, sub-2 Ω drops are microvolts, which is
the ±0.004% the table shows (read SNM rises microscopically; the degradation
sign is not uniform because the star resistors also load the forced-node
behavioral sources). The write bench resolves the margin only to its 25 mV
bit-line grid: both legs land in the same bin at all four corners, so any
write-margin shift smaller than ~12.5 mV is invisible to this data -- and
with RC time constants of ohms times sub-femtofarads (ps), none is expected
within the 1 ns pulse. What this evidence cannot distinguish: a sub-bin
write-margin shift from a genuine no-shift, and the DC-resistance part of a
delta from device-geometry/representation differences (the extraction's
device cards carry the layout-derived AS/AD/PS/PD areas; a `--device-only-leg`
run would split those, and was not part of this increment).

This is bitcell-level evidence for the T1 item 7 method on this repo; the
item itself stays `unmet` until the macro-level run after #30 (the spec's
signoff row is on the full array -- `ROADMAP.md`). Monte Carlo (#68) and the
wordline/bit-line wire-RC check remain separate items.

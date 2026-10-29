# bitcell characterization

Hold SNM, read SNM and write margin of the 6T cell in `design/bitcell/` at the
reference sizing, over the spec's 45 corners (`spec/sram.md`, Corner set).
Every number here is **simulated** (ngspice + PSP103 through OSDI), schematic
level: no parasitics, no Monte Carlo, no array.

```bash
sim/bitcell/run_bitcell.sh     # new record under records/<UTC>/, never overwritten
python3 sim/bitcell/test_bitcell_post.py
```

- `bench_snm.cir` + `request_snm.json`: DC butterfly, hold (WL low) and read (WL
  and both bit lines at VDD). The storage loop is broken by forcing one storage
  node of a full cell (instance a: force Q, read QB; instance b: force QB, read
  Q), so no device is duplicated outside the schematic. The sweep is normalised
  (0..1 x VDD) so it follows the supply corner.
- `bench_write.cir` + `request_write.json`: 33 cells, bit-line low level 0 to
  0.8 V in 25 mV steps, BLB at VDD, one 1 ns wordline pulse
  (`spec/write-pulse-width-decision.md`; `pw` in the bench, swept by the run). A cell flipped if Q < QB at the end of
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
and the rail-sharing decision are **not** done here.
`record.json` holds the summary, `grid_*.json`/`typical_*.json` every corner,
`curves/` the extracted voltage-transfer curves, `reports/` the `klt sim`
reports.

## Write-pulse window (record `records/20261029T225412Z/`)

The two open checks of `spec/write-pulse-width-decision.md`, run on the batch
fleet (klt 0.8.0 / ngspice 46) with the 1 ns pulse unchanged. Nothing in `spec/`
was edited; the decision record stays Proposed.

- **Flip time.** `tflip_0` is the time from 50 % WL rise to Q = QB for the cell
  with BL at 0 V, in all 45 corners (`grid_write.json`, `flip_time_s`). Slowest:
  **36.7 ps at mos_ss / 1.08 V / 125 C**, about 3.6 % of the 1.02 ns window
  between the 50 % wordline edges; every corner flips well inside it
  (`write_flip_time` in `record.json`). The window is not what limits the write.
- **0.5 / 1 / 2 ns sweep** (`write_pulse_sweep.json`, `sweep/`). The three worst
  write-margin corners of the 1 ns record are mos_sf / 1.08 V / -40 C (0.250 V),
  mos_sf / 1.08 V / 25 C (0.275 V) and a tie at 0.300 V (mos_ss and mos_tt,
  1.08 V, -40 C). `klt sim` corners are a Cartesian grid, so the sweep runs
  {sf, ss, tt} x 1.08 V x {-40, 25} C (6 corners), which contains all four.

  | Write margin (V) | 0.5 ns | 1 ns | 2 ns |
  |---|---|---|---|
  | mos_sf / 1.08 V / -40 C | 0.250 | 0.250 | 0.250 |
  | mos_sf / 1.08 V / 25 C | 0.275 | 0.275 | 0.300 |
  | mos_ss / 1.08 V / -40 C | 0.300 | 0.300 | 0.300 |
  | mos_tt / 1.08 V / -40 C | 0.300 | 0.300 | 0.300 |
  | mos_ss / 1.08 V / 25 C | 0.325 | 0.325 | 0.325 |
  | mos_tt / 1.08 V / 25 C | 0.325 | 0.350 | 0.350 |

  The margin depends weakly on the width: at most one 25 mV step between any two
  widths. The 1 ns column equals the 45-corner values for these corners.
  Both are schematic-level and, like everything above, simulated; the flip time
  is one cell with no bit-line or wordline RC.

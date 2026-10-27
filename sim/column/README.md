# sim/column

Nominal functional bench of the I/O column (`design/column/`): read of 0 and 1,
write of 0 and 1, at mos_tt, 1.20 V, 27 °C only. The corner grid, Monte Carlo,
access time and array-level margins are #26.

- `bench_read.cir`, `bench_write.cir`: two column copies each (real `bitcell`
  netlist, 127 unselected rows per bit line present, the half-selected cell of
  the unselected mux column present). Timelines are in the file headers.
- `column_post.py`: generates the `klt sim` requests, evaluates the
  measurements into per-case verdicts, builds the negative-control benches.
  `test_column_post.py` tests it without a simulator.
- `run_column.sh`: freshness check of the netlists, both benches, two negative
  controls (write-driver stacks at 0.15 µm; sense enable fired with the
  wordline), then `records/<UTC>/` (append-only).

Checks per case (limits are this bench's functional criteria, not spec values):
`OUT` resolves the stored value (|OUT−OUTB| > 1.0 V); bit-line differential at
the sense instant has the right sign; bit lines precharged (> 1.15 V) and
equalized (< 20 mV) before the wordline; selected and half-selected cells keep
their value; the unselected column's bit lines stay above 0.6 V. Write: flipped
at the end of the 1 ns pulse, flip time (from the 50 % point of the WL edge)
under 1 ns, value holds at 2.8 ns.

## Status

**Simulation NOT performed; no record exists.** `run_column.sh` has never run
to completion, and none of the verdict limits has been compared with a
measurement. On 2026-10-27 the batch submit failed: the fleet runner is klt
0.7.0 and refuses clients 0.8.0 and 0.8.1.dev55 (`batch_runner_version_mismatch`,
the only client on this host); klt 0.7.0 itself rejects `options.osdi_preload`
on the batch backend (and lacks `--report-out`). The bitcell record was made
with a 0.7.1 development client that no longer resolves. This host's ngspice 42
cannot load the OSDI v0.4 models, so no local run is possible either, and none
was attempted. Needed: a client compatible with the runner (or a runner
update), then `sim/column/run_column.sh`.

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

Record: `records/20261027T211740Z/` (nominal, mos_tt / 1.20 V / 27 C; batch job
`klt-sim-96ff8ca5102a`, runner klt 0.8.0, ngspice 46). `all_pass` is **false**.

- Read of 0 and of 1: the sense amp resolves the stored value, the bit-line
  differential has the right sign, precharge and equalize complete, both cells
  keep their value.
- Write of 0 and of 1: the cell flips 0.06-0.09 ns after the wordline midpoint
  (limit 1 ns) and the value holds at 2.8 ns.
- Negative controls: the 0.15 um write driver and the SAE-with-wordline read are
  both detected.
- **Failing check, all four cases: `unselected_column_bit_lines_hold`.** The
  unselected column's floating bit lines fall to about 0.07-0.08 V (limit
  0.6 V) while the wordline is high, because the half-selected cell discharges
  them. The limit was not relaxed. The cell itself keeps its value. Fixing it
  means keeping the unselected pair precharged (a per-pair precharge enable),
  which changes the column interface and is not done here.

A klt batch run whose corner errors exits 4; `run_column.sh` accepts that only for
the two negative controls (a driver that never flips the cell leaves the flip
time without a value, which is the detection) and only if the report exists.

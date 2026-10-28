#!/usr/bin/env bash
# run_all.sh -- cold-start invocation of every claimed measurement (T1 item 9, attest/item9.json).
#
# Prerequisites (sim/README.md "Cold start", steps 1-2, once per machine): the pinned PDK under
# PDK_ROOT and the OSDI build. Everything below goes to the batch fleet (`klt sim --backend batch`);
# a failed submit stops the run and nothing falls back to a local grid. The PDK smoke
# (sim/pdk-smoke/run_smoke.sh) is a setup check on a local ngspice >= 43, not a claimed measurement,
# so it is not run here.
#
#   1. sim/bitcell/run_bitcell.sh   hold SNM, read SNM, write margin of the cell, 45 corners
#   2. sim/column/run_column.sh     nominal functional bench of the I/O column
#   3. sim/array/run_array.sh       in-situ read SNM, write margin through the driver, access time, 45 corners
#
# Each step writes a new, never-overwritten records/<UTC>/ directory. Exit 0 iff every step exits 0.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${HERE}/bitcell/run_bitcell.sh"
"${HERE}/column/run_column.sh"
"${HERE}/array/run_array.sh"

#!/usr/bin/env bash
# netlist.sh [--check] [block ...] -- regenerate (default) or freshness-check
# (--check, exit 3 if any netlist is stale) every committed .spice in design/ from
# its xschem source; named blocks (e.g. gates/inv) restrict the run.
# Uses `klt netlist --block`; never run xschem directly (see design/README.md).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/.." && pwd)"
# shellcheck source=/dev/null
source "${REPO}/sim/harness/common/env.sh"
: "${PDK_ROOT:?netlist.sh: no PDK install resolved; see sim/README.md}"
command -v klt >/dev/null || { echo "netlist.sh: klt not on PATH" >&2; exit 3; }
MODE=""; [[ "${1:-}" == "--check" ]] && { MODE="--check"; shift; }
BLOCKS=(bitcell/bitcell column/precharge column/column_mux column/sense_amp column/write_driver column/column
  gates/inv gates/inv_x4 gates/nand2 gates/nand3 gates/nand4 gates/nor2
  decoder/predec3 decoder/predec4 decoder/wl_driver decoder/wl_drivers decoder/row_decoder
  latches/dlatch latches/addr_latch latches/data_latch latches/out_latch
  control/control macro/bl_pair macro/bit_slice macro/macro)
[[ $# -gt 0 ]] && BLOCKS=("$@")
rc=0
for b in "${BLOCKS[@]}"; do
  # run from the schematic's directory: xschem resolves relative symbol paths (../bitcell/...) against the cwd
  ( cd "${HERE}/$(dirname "${b}")" && klt netlist "$(basename "${b}").sch" -o "${HERE}/${b}.spice" --block ${MODE} \
    --rcfile "${HERE}/xschemrc" --pdk "${PDK}" --pdk-root "${PDK_ROOT}" >/dev/null ) || { echo "netlist.sh: ${b}.spice stale or failed" >&2; rc=3; }
  # xschem writes the schematic's absolute path on line 1; keep it repo-relative
  # (and the sym_path/sch_path of each expanded sub-block: drop the checkout prefix)
  [[ -z "${MODE}" ]] && sed -i -e "1s#.*#** sch_path: design/${b}.sch#" \
    -e "s#^\(\*\* s[a-z]*_path: \).*/design/#\1design/#" "${HERE}/${b}.spice"
done
exit "${rc}"

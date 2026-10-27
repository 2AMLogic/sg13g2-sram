#!/usr/bin/env bash
# netlist.sh -- regenerate (default) or freshness-check (--check, exit 3 if any
# netlist is stale) every committed .spice in design/ from its xschem source.
# Uses `klt netlist --block`; never run xschem directly (see design/README.md).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/.." && pwd)"
# shellcheck source=/dev/null
source "${REPO}/sim/harness/common/env.sh"
: "${PDK_ROOT:?netlist.sh: no PDK install resolved; see sim/README.md}"
command -v klt >/dev/null || { echo "netlist.sh: klt not on PATH" >&2; exit 3; }
MODE=""; [[ "${1:-}" == "--check" ]] && MODE="--check"
BLOCKS=(bitcell/bitcell column/precharge column/column_mux column/sense_amp column/write_driver column/column)
rc=0
for b in "${BLOCKS[@]}"; do
  klt netlist "${HERE}/${b}.sch" -o "${HERE}/${b}.spice" --block ${MODE} \
    --rcfile "${HERE}/xschemrc" --pdk "${PDK}" --pdk-root "${PDK_ROOT}" >/dev/null || { echo "netlist.sh: ${b}.spice stale or failed" >&2; rc=3; }
  # xschem writes the schematic's absolute path on line 1; keep it repo-relative
  [[ -z "${MODE}" ]] && sed -i "1s#.*#** sch_path: design/${b}.sch#" "${HERE}/${b}.spice"
done
exit "${rc}"

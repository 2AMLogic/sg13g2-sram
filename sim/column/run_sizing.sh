#!/usr/bin/env bash
# run_sizing.sh -- write-driver width sweep on the batch fleet (mos_tt, 1.20 V, 27 C).
#
# One write bench per width of the four driver NMOS stack devices (XMNA0/1, XMNB0/1; the
# inverter XMND is unchanged), submitted as ONE `klt sim --batch-set`. Never a local loop and
# never a local fallback: a failed submit exits 6. Output is append-only under
# sim/column/sizing/<UTC>/ (summary.json plus reports/w<W>.json per width).
# Usage: run_sizing.sh [width_um ...]   (default: 0.15 0.3 0.5 1.0 2.0 3.0)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${HERE}/.." && pwd)"
REPO="$(cd "${SIM_DIR}/.." && pwd)"
# shellcheck source=/dev/null
source "${SIM_DIR}/harness/common/env.sh"
# shellcheck source=/dev/null
source "${SIM_DIR}/harness/common/run_klt.sh"
: "${PDK_ROOT:?run_sizing.sh: no PDK install resolved; see sim/README.md}"
command -v klt >/dev/null || { echo "run_sizing.sh: klt not on PATH" >&2; exit 3; }
POST=(python3 -I "${HERE}/column_post.py")
WIDTHS=("$@"); [[ ${#WIDTHS[@]} -gt 0 ]] || WIDTHS=(0.15 0.3 0.5 1.0 2.0 3.0)

"${REPO}/design/netlist.sh" --check >/dev/null \
  || { echo "run_sizing.sh: a design/ netlist drifted from its schematic" >&2; exit 5; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REC="${HERE}/sizing/${STAMP}"
[[ -e "${REC}" ]] && { echo "run_sizing.sh: ${REC} exists (records are append-only)" >&2; exit 4; }
mkdir -p "${REC}/reports"
WORK="$(mktemp -d)"; trap 'rm -rf "${WORK}"' EXIT

REQS=()
for W in "${WIDTHS[@]}"; do
  D="${REC}/w${W}"; mkdir -p "${D}"
  sed -E "/^XMN[AB][01] /s/w=3\.0u/w=${W}u/" "${REPO}/design/column/column.spice" > "${D}/column_w.spice"
  grep -q "w=${W}u" "${D}/column_w.spice" || { echo "run_sizing.sh: width ${W} matched nothing" >&2; exit 7; }
  "${POST[@]}" negctl-bench "${HERE}/bench_write.cir" "${D}/bench_write.cir" --replace column.spice=./column_w.spice
  "${POST[@]}" request write "${D}/request.json" --netlist bench_write.cir
  REQS+=("${D}/request.json")
done

rc=0
klt sim --batch-set "${REQS[@]}" --max-in-flight 2 --capacity-retries 4 -o "${WORK}/out" --format json \
  > "${REC}/reports/set.json" 2> "${WORK}/set.stderr" || rc=$?
klt_redact_bucket < "${WORK}/set.stderr" > "${REC}/reports/set.stderr"
# exit 4 = an errored corner, expected for a driver too weak to flip the cell (no flip time).
if [[ "${rc}" -ne 0 && "${rc}" -ne 3 && "${rc}" -ne 4 ]]; then
  echo "run_sizing.sh: klt sim --batch-set failed (exit ${rc}); batch error, no local fallback:" >&2
  tail -5 "${REC}/reports/set.stderr" >&2
  exit 6
fi
# The per-width reports live in the scratch dir; keep them (the envelope only points there).
python3 -I - "${REC}" "${REC}/reports/set.json" <<'PY'
import json, shutil, sys
rec, env = sys.argv[1], sys.argv[2]
for r in json.load(open(env))["requests"]:
    if r.get("report"):
        shutil.copy(r["report"], f"{rec}/reports/{r['request'].split('/')[-2]}.json")
PY
python3 -I "${HERE}/column_post.py" sizing "sizing-${STAMP}" \
  $(for W in "${WIDTHS[@]}"; do echo "${W}=${REC}/reports/w${W}.json"; done) > "${REC}/summary.json"
echo "batch-set done (exit ${rc}); envelope: ${REC}/reports/set.json" >&2

#!/usr/bin/env bash
# run_column.sh -- nominal functional bench of the I/O column (mos_tt, 1.20 V, 27 C):
# read of 0 and 1, write of 0 and 1, plus two negative controls.
#
# Steps:
#   1. design/netlist.sh --check bitcell/bitcell column/column: both netlists match their schematics (exit 5 if stale).
#   2. bench_read.cir and bench_write.cir, one `klt sim` request each (batch fleet).
#   3. Negative controls: (a) write driver stacks at 0.15 um must fail to write inside the
#      1 ns pulse; (b) SAE fired with the wordline (no bit-line differential) must not
#      resolve both stored values. Each must produce a failing case or the script fails.
#   4. record.json under sim/column/records/<UTC>/ (append-only, never overwritten).
#
# Backend: batch only (`--backend batch`); a failed submit exits 6 and never falls back to a
# local run. The client klt must match the fleet runner's version (sim/column/README.md).
# Exit 0 iff all cases pass and both negative controls are detected.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${HERE}/.." && pwd)"
REPO="$(cd "${SIM_DIR}/.." && pwd)"
# shellcheck source=/dev/null
source "${SIM_DIR}/harness/common/env.sh"
# shellcheck source=/dev/null
source "${SIM_DIR}/harness/common/run_klt.sh"
: "${PDK_ROOT:?run_column.sh: no PDK install resolved; see sim/README.md}"
command -v klt >/dev/null || { echo "run_column.sh: klt not on PATH" >&2; exit 3; }
POST=(python3 -I "${HERE}/column_post.py")

# bitcell and column only: `design/netlist.sh --check` also flags control/bit_slice/macro from the
# checkout-specific sym_path/sch_path comment lines of nested blocks, which this bench does not use.
"${REPO}/design/netlist.sh" --check bitcell/bitcell column/column >/dev/null \
  || { echo "run_column.sh: a design/ netlist drifted from its schematic (regenerate: design/README.md)" >&2; exit 5; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REC="${HERE}/records/${STAMP}"
[[ -e "${REC}" ]] && { echo "run_column.sh: ${REC} exists (records are append-only)" >&2; exit 4; }
mkdir -p "${REC}/reports" "${REC}/negctl"
WORK="$(mktemp -d)"; trap 'rm -rf "${WORK}"' EXIT


# --- nominal read and write ---------------------------------------------------
"${POST[@]}" request read "${HERE}/.req_read.json"
"${POST[@]}" request write "${HERE}/.req_write.json"
trap 'rm -rf "${WORK}" "${HERE}/.req_read.json" "${HERE}/.req_write.json"' EXIT
run_klt "${HERE}/.req_read.json" read
run_klt "${HERE}/.req_write.json" write

# --- negative controls ----------------------------------------------------------
# column.spice embeds the write driver and the benches include nothing else, so weaken the embedded copy.
sed -E '/^XMN[AB][01] /s/w=3\.0u/w=0.15u/' "${REPO}/design/column/column.spice" > "${REC}/negctl/column_weak.spice"
grep -q 'w=0\.15u' "${REC}/negctl/column_weak.spice" || { echo "run_column.sh: write-driver weakening matched nothing" >&2; exit 7; }
"${POST[@]}" negctl-bench "${HERE}/bench_write.cir" "${REC}/negctl/bench_write.cir" --replace column.spice=./column_weak.spice
"${POST[@]}" request write "${REC}/negctl/request_write.json" --netlist bench_write.cir
"${POST[@]}" negctl-bench "${HERE}/bench_read.cir" "${REC}/negctl/bench_read.cir" --sae-delay-ns 0.8
"${POST[@]}" request read "${REC}/negctl/request_read.json" --netlist bench_read.cir
run_klt "${REC}/negctl/request_write.json" negctl_write 1
run_klt "${REC}/negctl/request_read.json" negctl_read 1

# --- post-process and record ----------------------------------------------------
"${POST[@]}" read "${REC}/reports/read.json.gz" nominal > "${REC}/read.json"
"${POST[@]}" write "${REC}/reports/write.json.gz" nominal > "${REC}/write.json"
"${POST[@]}" write "${REC}/reports/negctl_write.json.gz" negctl_weak_write_driver > "${REC}/negctl_write.json"
"${POST[@]}" read "${REC}/reports/negctl_read.json.gz" negctl_early_sae > "${REC}/negctl_read.json"

PDKTAG="$(grep -o '"release_tag": *"[^"]*"' "${SIM_DIR}/pdk.json" | head -1 | cut -d'"' -f4)"
python3 -I - "${REC}" "${STAMP}" "${PDKTAG}" <<'PY'
import gzip, json, sys
rec, stamp, pdktag = sys.argv[1:4]
L = lambda n: json.load(open(f"{rec}/{n}.json"))
rd, wr, nw, nr = L("read"), L("write"), L("negctl_write"), L("negctl_read")
env = json.load(gzip.open(f"{rec}/reports/read.json.gz", "rt"))["environment"]
remote = env.get("remote", {})
ok = rd["all_pass"] and wr["all_pass"] and nw["any_fail"] and nr["any_fail"] \
     and "error" not in rd and "error" not in wr
out = {
  "stamp": stamp, "kind": "simulated", "pdk_release_tag": pdktag,
  "corner": "mos_tt, 1.20 V, 27 C (nominal only; the corner grid is #26)",
  "organization": "mux 2, 128 cells per bit line, 2 bit-line pairs per I/O column",
  "engine": {"version_banner": env.get("engine_build", {}).get("version_banner"),
             "batch_job_ids": remote.get("job_id"), "runner_klt_version": remote.get("runner_klt_version")},
  "read": {c: v["pass"] for c, v in rd["cases"].items()},
  "write": {c: {"pass": v["pass"], "flip_time_ns": v.get("flip_time_ns")} for c, v in wr["cases"].items()},
  "negative_controls": {"weak_write_driver_detected": nw["any_fail"], "early_sae_detected": nr["any_fail"]},
  "all_pass": ok,
}
json.dump(out, open(f"{rec}/record.json", "w"), indent=2); open(f"{rec}/record.json", "a").write("\n")
print(json.dumps(out, indent=2))
sys.exit(0 if ok else 1)
PY

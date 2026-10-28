#!/usr/bin/env bash
# run_array.sh -- array-level benches over the spec's 45 corners (spec/sram.md): in-situ read SNM,
# write margin through the real write driver, access time and write completion.
#
# Usage:  sim/array/run_array.sh [--typical]
#   --typical   one corner (mos_tt, 1.20 V, 25 C) instead of the 45-corner grid (debug probe).
#
# Steps:
#   1. design/netlist.sh --check for bitcell and column (netlists match schematics) and bench_access.cir matches macro.spice.
#   2. Negative controls at the typical point: (a) SNM with beta 0.25 cells must read a lower SNM than the
#      reference; (b) a 0.15 um write driver must fail the write bench; (c) the same driver must fail the
#      access bench (the cell never flips, the read returns the old value).
#   3. The three benches over the grid: three `klt sim` requests on the batch fleet.
#   4. records/<UTC>/ (append-only): reports, per-bench verdicts, record.json.
#
# Backend: batch only (`--backend batch`); a failed submit exits 6 and never falls back to a local run.
# Exit 0 iff every step ran and all three negative controls were detected; failing corners are RECORDED
# (record.json), not hidden and not a script error.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${HERE}/.." && pwd)"
REPO="$(cd "${SIM_DIR}/.." && pwd)"
# shellcheck source=/dev/null
source "${SIM_DIR}/harness/common/env.sh"
# shellcheck source=/dev/null
source "${SIM_DIR}/harness/common/run_klt.sh"
: "${PDK_ROOT:?run_array.sh: no PDK install resolved; see sim/README.md}"
command -v klt >/dev/null || { echo "run_array.sh: klt not on PATH" >&2; exit 3; }
POST=(python3 -I "${HERE}/array_post.py")
TYPICAL=()
[[ "${1:-}" == "--typical" ]] && TYPICAL=(--typical)

# Only the column and bitcell netlists are freshness-checked here. `design/netlist.sh --check` also reports
# control/bit_slice/macro as stale from the checkout-specific sym_path/sch_path comment lines that nested blocks
# carry (a comparison artifact, not a design change), so it cannot gate a run; bench_access.cir is instead
# checked against the committed macro.spice below.
"${REPO}/design/netlist.sh" --check bitcell/bitcell column/column >/dev/null \
  || { echo "run_array.sh: a design/ netlist drifted from its schematic (regenerate: design/README.md)" >&2; exit 5; }
"${POST[@]}" gen-access "${REPO}/design/macro/macro.spice" "${HERE}/bench_access.cir" --check \
  || { echo "run_array.sh: bench_access.cir is stale (regenerate: array_post.py gen-access)" >&2; exit 5; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REC="${HERE}/records/${STAMP}"
[[ -e "${REC}" ]] && { echo "run_array.sh: ${REC} exists (records are append-only)" >&2; exit 4; }
mkdir -p "${REC}/reports" "${REC}/curves" "${REC}/negctl"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}" "${HERE}"/.req_*.json' EXIT


# --- negative controls (mos_tt, 1.20 V, 25 C, a grid corner) --------------------------------------------------------
COL="${REPO}/design/column/column.spice"
"${POST[@]}" weaken "${COL}" "${REC}/negctl/column_beta.spice" snm
"${POST[@]}" weaken "${COL}" "${REC}/negctl/column_weakdrv.spice" write
"${POST[@]}" negctl-bench "${HERE}/bench_snm.cir" "${REC}/negctl/bench_snm.cir" --replace column.spice=./column_beta.spice
"${POST[@]}" negctl-bench "${HERE}/bench_write.cir" "${REC}/negctl/bench_write.cir" --replace column.spice=./column_weakdrv.spice
# the access bench takes the write driver from macro.spice
sed -E '/^XMN[AB][01] /s/w=3\.0u/w=0.15u/' "${REPO}/design/macro/macro.spice" > "${REC}/negctl/macro_weakdrv.spice"
grep -q 'w=0\.15u' "${REC}/negctl/macro_weakdrv.spice" || { echo "run_array.sh: write-driver weakening matched nothing" >&2; exit 7; }
"${POST[@]}" negctl-bench "${HERE}/bench_access.cir" "${REC}/negctl/bench_access.cir" --replace macro.spice=./macro_weakdrv.spice
for b in snm write access; do
  "${POST[@]}" request "${b}" "${REC}/negctl/request_${b}.json" --typical --netlist bench_${b}.cir
  run_klt "${REC}/negctl/request_${b}.json" "negctl_${b}" 1
done

# --- the grid ---------------------------------------------------------------------------------
for b in snm write access; do
  "${POST[@]}" request "${b}" "${HERE}/.req_${b}.json" "${TYPICAL[@]}"
  run_klt "${HERE}/.req_${b}.json" "${b}" 1
done

# --- post-process and record --------------------------------------------------------------------
"${POST[@]}" snm "${REC}/reports/snm.json.gz" "${REC}/curves" grid > "${REC}/snm.json"
"${POST[@]}" write "${REC}/reports/write.json.gz" grid > "${REC}/write.json"
"${POST[@]}" access "${REC}/reports/access.json.gz" grid > "${REC}/access.json"
"${POST[@]}" snm "${REC}/reports/negctl_snm.json.gz" "${REC}/curves" negctl_beta > "${REC}/negctl_snm.json"
"${POST[@]}" write "${REC}/reports/negctl_write.json.gz" negctl_weak_driver > "${REC}/negctl_write.json"
"${POST[@]}" access "${REC}/reports/negctl_access.json.gz" negctl_weak_driver > "${REC}/negctl_access.json"

PDKTAG="$(grep -o '"release_tag": *"[^"]*"' "${SIM_DIR}/pdk.json" | head -1 | cut -d'"' -f4)"
python3 -I - "${REC}" "${STAMP}" "${PDKTAG}" "${TYPICAL[*]:-}" <<'PY'
import gzip, json, sys
rec, stamp, pdktag, typical = sys.argv[1:5]
L = lambda n: json.load(open(f"{rec}/{n}.json"))
snm, wr, ac = L("snm"), L("write"), L("access")
nsnm, nwr, nac = L("negctl_snm"), L("negctl_write"), L("negctl_access")
env = json.load(gzip.open(f"{rec}/reports/access.json.gz", "rt"))["environment"]
remote = env.get("remote", {})
def jobs(n):
    return json.load(gzip.open(f"{rec}/reports/{n}.json.gz", "rt"))["environment"].get("remote", {}).get("job_id")
def worst(rows, key):
    vals = [(r[key], r["corner_id"]) for r in rows if isinstance(r.get(key), (int, float))]
    return min(vals) if vals else None
def slowest(rows, key):
    vals = [(r[key], r["corner_id"]) for r in rows if isinstance(r.get(key), (int, float))]
    return max(vals) if vals else None
# negative control (a): SNM must drop below the reference at the typical point
ref = next((r.get("read_snm_v") for r in snm["corners"] if r["corner_id"] == "mos_tt/1.200V/25C"), None)
neg = nsnm["corners"][0].get("read_snm_v")
det = {"beta_cell_lowers_read_snm": isinstance(neg, (int, float)) and isinstance(ref, (int, float)) and neg < ref,
       "weak_driver_fails_write_bench": nwr["any_fail"], "weak_driver_fails_access_bench": nac["any_fail"]}
out = {
  "stamp": stamp, "kind": "simulated", "pdk_release_tag": pdktag,
  "scope": "typical point only (--typical)" if typical else "45 corners: 5 process x 3 supply x 3 temperature (spec/sram.md)",
  "organization": "mux 2, 128 cells per bit line, 2 bit-line pairs per I/O; access bench: full control/decode/latches + 1 real bit slice + load of the other 31",
  "engine": {"version_banner": env.get("engine_build", {}).get("version_banner"), "runner_klt_version": remote.get("runner_klt_version"),
             "batch_job_ids": {n: jobs(n) for n in ("snm", "write", "access", "negctl_snm", "negctl_write", "negctl_access")}},
  "read_snm_in_situ": {"corners": snm["corner_count"], "worst_v": worst(snm["corners"], "read_snm_v"), "failing_corners": snm["failing_corners"]},
  "write_margin": {"corners": wr["corner_count"], "worst_v": worst(wr["corners"], "write_margin_v"), "failing_corners": wr["failing_corners"]},
  "access": {"corners": ac["corner_count"],
             "slowest_read1_ns": slowest(ac["corners"], "read1_access_ns"), "slowest_read0_ns": slowest(ac["corners"], "read0_access_ns"),
             "slowest_write1_flip_after_clk_ns": slowest(ac["corners"], "write1_flip_after_clk_ns"),
             "slowest_write0_flip_after_clk_ns": slowest(ac["corners"], "write0_flip_after_clk_ns"),
             "failing_corners": ac["failing_corners"]},
  "negative_controls_detected": det,
  "all_corners_pass": not (snm["any_fail"] or wr["any_fail"] or ac["any_fail"]),
  "not_established": ["Monte Carlo (separate evidence item)", "parasitic-extracted timing", "wire RC on wordline and bit lines"],
}
json.dump(out, open(f"{rec}/record.json", "w"), indent=2); open(f"{rec}/record.json", "a").write("\n")
print(json.dumps(out, indent=2))
sys.exit(0 if all(det.values()) else 1)
PY

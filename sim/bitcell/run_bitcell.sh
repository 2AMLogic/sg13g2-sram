#!/usr/bin/env bash
# run_bitcell.sh -- 6T bitcell hold SNM, read SNM and write margin (design item,
# spec/sram.md "What must be measured"), reference sizing from
# spec/bitcell-decision.md evidence 1.
#
# What runs (every number is labelled `simulated`; nothing here is a spec value):
#   1. klt netlist --check: design/bitcell/bitcell.spice still matches bitcell.sch.
#   2. Typical point (mos_tt, 1.20 V, 27 C): hold/read SNM and write margin.
#   3. Negative control at the typical point: pull-downs halved and access devices doubled (beta 0.25); the
#      read SNM must come out below the reference cell's or the script fails.
#   4. The 45-corner grid (5 process x 3 temp x 3 supply) for SNM and for write
#      margin: two `klt sim` requests, submitted to the batch fleet.
# Hold/read SNM: sim/bitcell/bench_snm.cir (DC butterfly). Write margin:
# sim/bitcell/bench_write.cir (1 ns wordline pulse, 33 bit-line levels).
#
# Backend policy: all `klt sim` runs use the batch fleet (`--backend batch`),
# including the single typical point, because this host's ngspice (42) cannot
# load the OSDI v0.4 models locally (see sim/README.md). A failed submit is
# reported and the script exits non-zero; it never falls back to a local loop.
#
# Usage (after sim/README.md "Cold start" step 1):
#   sim/bitcell/run_bitcell.sh
# Writes a new, never-overwritten record under sim/bitcell/records/<UTC>/.
# Exit 0 iff every step ran and the negative control was detected; hold SNM,
# read SNM and write margin that are not strictly positive are RECORDED as
# failing corners (verdict in record.json), not hidden and not a script error.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${HERE}/.." && pwd)"
REPO="$(cd "${SIM_DIR}/.." && pwd)"
# shellcheck source=/dev/null
source "${SIM_DIR}/harness/common/env.sh"
# shellcheck source=/dev/null
source "${SIM_DIR}/harness/common/run_klt.sh"
: "${PDK_ROOT:?run_bitcell.sh: no PDK install resolved; see sim/README.md}"
command -v klt >/dev/null || { echo "run_bitcell.sh: klt not on PATH" >&2; exit 3; }
POST=(python3 -I "${HERE}/bitcell_post.py")

klt netlist "${REPO}/design/bitcell/bitcell.sch" -o "${REPO}/design/bitcell/bitcell.spice" \
  --block --check --rcfile "${REPO}/design/xschemrc" --pdk "${PDK}" --pdk-root "${PDK_ROOT}" >/dev/null \
  || { echo "run_bitcell.sh: bitcell.spice drifted from bitcell.sch (regenerate: design/README.md)" >&2; exit 5; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REC="${HERE}/records/${STAMP}"
[[ -e "${REC}" ]] && { echo "run_bitcell.sh: ${REC} exists (records are append-only)" >&2; exit 4; }
mkdir -p "${REC}/reports" "${REC}/curves" "${REC}/negctl"
WORK="$(mktemp -d)"; trap 'rm -rf "${WORK}"' EXIT


# --- typical point -----------------------------------------------------------
"${POST[@]}" typical-request "${HERE}/request_snm.json" "${HERE}/.typ_snm.json" --netlist bench_snm.cir
"${POST[@]}" typical-request "${HERE}/request_write.json" "${HERE}/.typ_write.json" --netlist bench_write.cir
trap 'rm -rf "${WORK}" "${HERE}/.typ_snm.json" "${HERE}/.typ_write.json"' EXIT
run_klt "${HERE}/.typ_snm.json" typical_snm
run_klt "${HERE}/.typ_write.json" typical_write

# --- negative control: pull-downs halved and access devices doubled (beta 0.25) ---------------------------
sed -e '/^XMN[01] /s/w=0.30u/w=0.15u/' -e '/^XMN[23] /s/w=0.30u/w=0.60u/' "${REPO}/design/bitcell/bitcell.spice" > "${REC}/negctl/bitcell_negctl.spice"
"${POST[@]}" negctl-bench "${HERE}/bench_snm.cir" "${REC}/negctl/bench_snm.cir" ./bitcell_negctl.spice
"${POST[@]}" typical-request "${HERE}/request_snm.json" "${REC}/negctl/request_snm.json" --netlist bench_snm.cir
run_klt "${REC}/negctl/request_snm.json" negctl_snm

# --- 45-corner grid -----------------------------------------------------------
run_klt "${HERE}/request_snm.json" grid_snm
run_klt "${HERE}/request_write.json" grid_write

# --- post-process and record --------------------------------------------------
"${POST[@]}" snm "${REC}/reports/typical_snm.json.gz" "${WORK}/typical_snm" "${REC}/curves" typical > "${REC}/typical_snm.json"
"${POST[@]}" write "${REC}/reports/typical_write.json.gz" typical > "${REC}/typical_write.json"
"${POST[@]}" snm "${REC}/reports/negctl_snm.json.gz" "${WORK}/negctl_snm" "${REC}/curves" negctl > "${REC}/negctl_snm.json"
"${POST[@]}" snm "${REC}/reports/grid_snm.json.gz" "${WORK}/grid_snm" "${REC}/curves" grid > "${REC}/grid_snm.json"
"${POST[@]}" write "${REC}/reports/grid_write.json.gz" grid > "${REC}/grid_write.json"

PDKTAG="$(grep -o '"release_tag": *"[^"]*"' "${SIM_DIR}/pdk.json" | head -1 | cut -d'"' -f4)"
python3 -I - "${REC}" "${STAMP}" "${PDKTAG}" <<'PY'
import gzip, json, sys
rec, stamp, pdktag = sys.argv[1:4]
L = lambda n: json.load(open(f"{rec}/{n}.json"))
env = json.load(gzip.open(f"{rec}/reports/grid_snm.json.gz", "rt"))["environment"]
remote = env.get("remote", {})
typ, tw, neg, gs, gw = L("typical_snm"), L("typical_write"), L("negctl_snm"), L("grid_snm"), L("grid_write")
pos = lambda v: v is not None and v > 0
def worst(rows, key):
    vals = [(r[key], r["corner_id"]) for r in rows if r.get(key) is not None]
    return min(vals) if vals else None
errs = [r["corner_id"] for r in gs["corners"] + gw["corners"] if "error" in r]
t_hold, t_read = typ["corners"][0].get("hold_snm_v"), typ["corners"][0].get("read_snm_v")
n_read = neg["corners"][0].get("read_snm_v")
out = {
  "stamp": stamp, "kind": "simulated", "pdk_release_tag": pdktag,
  "cell": "6T, pull-down sg13_lv_nmos 300n/130n, pull-up sg13_lv_pmos 150n/130n, access sg13_lv_nmos 300n/130n (spec/bitcell-decision.md evidence 1)",
  "engine": {"version_banner": env.get("engine_build", {}).get("version_banner"), "batch_job_ids": remote.get("job_id"), "runner_klt_version": remote.get("runner_klt_version")},
  "snm_method": "inscribed square (Seevinck), exact on the sampled polylines; snm_extract.py vertical-gap value recorded as *_snm_vgap_v (over-reads)",
  "write_margin_method": "highest constant bit-line low level (25 mV grid, 0..0.8 V) at which the cell flips within one 1 ns wordline pulse; BLB at VDD",
  "typical": {"corner": typ["corners"][0]["corner_id"], "hold_snm_v": t_hold, "read_snm_v": t_read,
             "write_margin_v": tw["corners"][0].get("write_margin_v")},
  "negative_control": {"what": "pull-downs 150n, access 600n (beta 0.25)", "read_snm_v": n_read,
                       "detected": n_read is not None and t_read is not None and n_read < t_read},
  "grid": {"corners": len(gs["corners"]),
           "worst_hold_snm_v": worst(gs["corners"], "hold_snm_v"),
           "worst_read_snm_v": worst(gs["corners"], "read_snm_v"),
           "worst_write_margin_v": worst(gw["corners"], "write_margin_v"),
           "corners_not_strictly_positive": sorted({r["corner_id"] for r in gs["corners"] if not (pos(r.get("hold_snm_v")) and pos(r.get("read_snm_v")))}
                                                   | {r["corner_id"] for r in gw["corners"] if not pos(r.get("write_margin_v"))}),
           "corners_with_errors": errs},
  "not_established": ["write flip time at mos_ss/1.08 V/125 C (spec/write-pulse-width-decision.md open item)",
                      "0.5/1/2 ns pulse sensitivity", "Monte Carlo (separate evidence item)", "rail sharing decision"],
}
json.dump(out, open(f"{rec}/record.json", "w"), indent=2); open(f"{rec}/record.json", "a").write("\n")
print(json.dumps(out, indent=2))
sys.exit(0 if out["negative_control"]["detected"] and not errs else 1)
PY

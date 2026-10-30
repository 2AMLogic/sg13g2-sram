#!/usr/bin/env bash
# run_bitcell_mc.sh -- mismatch Monte Carlo of the 6T bitcell's hold SNM, read SNM and write
# margin (spec/sram.md, Margins row and "Statistical treatment"). It adds to the 45-corner
# deterministic record (run_bitcell.sh); it never replaces it.
#
# What runs (every number is labelled `simulated`; nothing here is a spec value):
#   per corner point (default: the five below), on the batch fleet:
#     1. mismatch MC of bench_snm.cir      (hold/read SNM; `<corner>_mismatch` model sections)
#     2. mismatch MC of bench_write_mc.cir (write margin; one cell, 33 bit-line levels in series)
#     3. the same write bench without MC   (must reproduce the 45-corner record's write margin)
#   negative control: the beta 0.25 cell (as run_bitcell.sh) under the same MC at two points; its
#     read SNM must sit clearly below the reference cell's (mean gap > 3 sigma) or this fails.
#   determinism: the typical-point SNM MC run twice with the same seed must give identical samples.
#   activity: klt must report the MOS family's mismatch active, and the two identical cell
#     instances of the SNM bench must differ in every sample (asymmetry > 0).
#   `klt yield` per corner point: lower limit 0 V (strictly positive), Cpk, sigma-to-spec, exact
#     empirical-yield bound, sample-size verdict. No numeric target_yield is set.
#
# Corner points (reason): mos_tt/1.20/27 typical; mos_fs/1.08/125 bounds read SNM; mos_sf/1.08/-40
# bounds write margin; mos_ff/1.08/125 bounds hold SNM; mos_ss/1.08/125 is the slow-write corner of
# the write-pulse open item. Override with MC_POINTS="proc vdd temp;proc vdd temp;...".
#
# Backend policy: batch fleet only (run_klt). A failed submit is reported and the script exits
# non-zero; it never falls back to a local loop.
#
# Usage (after sim/README.md "Cold start" step 1):
#   MC_N=300 MC_SEED=20261029 sim/bitcell/run_bitcell_mc.sh
# `klt yield` needs the klt_yield_native extension; if the host klt lacks it point
# KLT_YIELD_PYTHONPATH at a directory holding it (a throwaway one, never a host install).
# Writes a new, never-overwritten record under sim/bitcell/mc/records/<UTC>/. Exit 0 iff every
# step ran and every gate above held; margins that are not strictly positive in some sample are
# RECORDED (record.json), not hidden and not a script error.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${HERE}/.." && pwd)"
REPO="$(cd "${SIM_DIR}/.." && pwd)"
# shellcheck source=/dev/null
source "${SIM_DIR}/harness/common/env.sh"
# shellcheck source=/dev/null
source "${SIM_DIR}/harness/common/run_klt.sh"
: "${PDK_ROOT:?run_bitcell_mc.sh: no PDK install resolved; see sim/README.md}"
command -v klt >/dev/null || { echo "run_bitcell_mc.sh: klt not on PATH" >&2; exit 3; }
POST=(python3 -I "${HERE}/bitcell_post.py")

MC_N="${MC_N:-300}"
MC_SEED="${MC_SEED:-20261029}"
MC_POINTS="${MC_POINTS:-mos_tt 1.20 27;mos_fs 1.08 125;mos_sf 1.08 -40;mos_ff 1.08 125;mos_ss 1.08 125}"
NEGCTL_POINTS="${NEGCTL_POINTS:-mos_tt 1.20 27;mos_fs 1.08 125}"
KLT_YIELD=(env "PYTHONPATH=${KLT_YIELD_PYTHONPATH:-}" klt yield)
# fail early, before any fleet job, if klt yield cannot run
PROBE="$(mktemp -d)"; printf '{"measurements":[{"name":"x","samples":[1,2,3],"limits":{"min":0}}]}' > "${PROBE}/p.json"
"${KLT_YIELD[@]}" "${PROBE}/p.json" --format json >/dev/null 2>&1 \
  || { echo "run_bitcell_mc.sh: klt yield unavailable (klt_yield_native missing); set KLT_YIELD_PYTHONPATH" >&2; exit 3; }
rm -rf "${PROBE}"

klt netlist "${REPO}/design/bitcell/bitcell.sch" -o "${REPO}/design/bitcell/bitcell.spice" \
  --block --check --rcfile "${REPO}/design/xschemrc" --pdk "${PDK}" --pdk-root "${PDK_ROOT}" >/dev/null \
  || { echo "run_bitcell_mc.sh: bitcell.spice drifted from bitcell.sch (regenerate: design/README.md)" >&2; exit 5; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REC="${HERE}/mc/records/${STAMP}"
[[ -e "${REC}" ]] && { echo "run_bitcell_mc.sh: ${REC} exists (records are append-only)" >&2; exit 4; }
mkdir -p "${REC}/reports" "${REC}/samples" "${REC}/yield" "${REC}/negctl"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}" "${HERE}"/.mc_*.json' EXIT

ptag() { local t="${3/-/m}"; echo "${1}_${2}_${t}"; }   # mos_sf 1.08 -40 -> mos_sf_1.08_m40
IFS=';' read -r -a POINTS <<< "${MC_POINTS}"
IFS=';' read -r -a NEGPOINTS <<< "${NEGCTL_POINTS}"

# --- negative-control cell: pull-downs halved and access devices doubled (beta 0.25) -----------------
sed -e '/^XMN[01] /s/w=0.30u/w=0.15u/' -e '/^XMN[23] /s/w=0.30u/w=0.60u/' "${REPO}/design/bitcell/bitcell.spice" > "${REC}/negctl/bitcell_negctl.spice"
"${POST[@]}" negctl-bench "${HERE}/bench_snm.cir" "${REC}/negctl/bench_snm.cir" ./bitcell_negctl.spice

# --- fleet runs ----------------------------------------------------------------------------------
for pt in "${POINTS[@]}"; do
  read -r proc vdd temp <<< "${pt}"; tag="$(ptag "${proc}" "${vdd}" "${temp}")"
  "${POST[@]}" mc-request "${HERE}/request_snm_mc.json" "${HERE}/.mc_snm.json" "${proc}" "${vdd}" "${temp}" "${MC_N}" "${MC_SEED}"
  run_klt "${HERE}/.mc_snm.json" "mc_snm_${tag}"
  "${POST[@]}" mc-request "${HERE}/request_write_mc.json" "${HERE}/.mc_write.json" "${proc}" "${vdd}" "${temp}" "${MC_N}" "${MC_SEED}"
  run_klt "${HERE}/.mc_write.json" "mc_write_${tag}"
  "${POST[@]}" mc-request "${HERE}/request_write_mc.json" "${HERE}/.mc_write.json" "${proc}" "${vdd}" "${temp}" 0 0
  run_klt "${HERE}/.mc_write.json" "det_write_${tag}"
done
for pt in "${NEGPOINTS[@]}"; do
  read -r proc vdd temp <<< "${pt}"; tag="$(ptag "${proc}" "${vdd}" "${temp}")"
  "${POST[@]}" mc-request "${HERE}/request_snm_mc.json" "${REC}/negctl/request_snm_${tag}.json" "${proc}" "${vdd}" "${temp}" "${MC_N}" "${MC_SEED}" --netlist bench_snm.cir
  run_klt "${REC}/negctl/request_snm_${tag}.json" "mc_negctl_snm_${tag}"
done
# determinism: same seed again at the first point
read -r proc vdd temp <<< "${POINTS[0]}"; tag0="$(ptag "${proc}" "${vdd}" "${temp}")"
"${POST[@]}" mc-request "${HERE}/request_snm_mc.json" "${HERE}/.mc_snm.json" "${proc}" "${vdd}" "${temp}" "${MC_N}" "${MC_SEED}"
run_klt "${HERE}/.mc_snm.json" "mc_snm_${tag0}_rerun"

# --- post-process --------------------------------------------------------------------------------
for pt in "${POINTS[@]}"; do
  read -r proc vdd temp <<< "${pt}"; tag="$(ptag "${proc}" "${vdd}" "${temp}")"
  "${POST[@]}" mc-snm "${REC}/reports/mc_snm_${tag}.json.gz" "${tag}" > "${REC}/samples/snm_${tag}.json"
  "${POST[@]}" mc-write "${REC}/reports/mc_write_${tag}.json.gz" "${tag}" > "${REC}/samples/write_${tag}.json"
  "${POST[@]}" write "${REC}/reports/det_write_${tag}.json.gz" "${tag}" > "${REC}/samples/det_write_${tag}.json"
  "${POST[@]}" mc-yield-set "${REC}/samples/snm_${tag}.json" "${REC}/samples/write_${tag}.json" "${REC}/yield/set_${tag}.json"
  "${KLT_YIELD[@]}" "${REC}/yield/set_${tag}.json" --format json > "${REC}/yield/yield_${tag}.json"
done
for pt in "${NEGPOINTS[@]}"; do
  read -r proc vdd temp <<< "${pt}"; tag="$(ptag "${proc}" "${vdd}" "${temp}")"
  "${POST[@]}" mc-snm "${REC}/reports/mc_negctl_snm_${tag}.json.gz" "negctl_${tag}" > "${REC}/samples/negctl_snm_${tag}.json"
done
"${POST[@]}" mc-snm "${REC}/reports/mc_snm_${tag0}_rerun.json.gz" "${tag0}_rerun" > "${REC}/samples/snm_${tag0}_rerun.json"

# --- gates and record ----------------------------------------------------------------------------
GATES=0
for pt in "${NEGPOINTS[@]}"; do
  read -r proc vdd temp <<< "${pt}"; tag="$(ptag "${proc}" "${vdd}" "${temp}")"
  "${POST[@]}" mc-negctl "${REC}/samples/snm_${tag}.json" "${REC}/samples/negctl_snm_${tag}.json" > "${REC}/negctl/result_${tag}.txt" || GATES=1
done
"${POST[@]}" mc-same "${REC}/samples/snm_${tag0}.json" "${REC}/samples/snm_${tag0}_rerun.json" > "${REC}/determinism.txt" || GATES=1

PDKTAG="$(grep -o '"release_tag": *"[^"]*"' "${SIM_DIR}/pdk.json" | head -1 | cut -d'"' -f4)"
python3 -I - "${REC}" "${STAMP}" "${PDKTAG}" "${MC_N}" "${MC_SEED}" "${GATES}" "${HERE}/records" "$(IFS=';'; echo "${POINTS[*]}")" "$(IFS=';'; echo "${NEGPOINTS[*]}")" <<'PY'
import glob, gzip, json, sys
rec, stamp, pdktag, n, seed, gates, detdir, points, negpoints = sys.argv[1:10]
n, seed, gates = int(n), int(seed), int(gates)
points = [p.split() for p in points.split(";")]
negpoints = [p.split() for p in negpoints.split(";")]
tag = lambda p: f"{p[0]}_{p[1]}_{p[2].replace('-', 'm', 1)}"
L = lambda path: json.load(open(f"{rec}/{path}"))
# deterministic write margins (45-corner grid and typical point), newest record wins
det_ref = {}
for f in sorted(glob.glob(f"{detdir}/*/grid_write.json") + glob.glob(f"{detdir}/*/typical_write.json")):
    det_ref.update({c["corner_id"]: c.get("write_margin_v") for c in json.load(open(f))["corners"]})
problems, out_pts = [], []
env = {}
for p in points:
    t = tag(p)
    rep = json.load(gzip.open(f"{rec}/reports/mc_snm_{t}.json.gz", "rt"))
    env = rep["environment"]
    snm, wr, dw, y = L(f"samples/snm_{t}.json"), L(f"samples/write_{t}.json"), L(f"samples/det_write_{t}.json"), L(f"yield/yield_{t}.json")
    fam = {f["family"]: f["active"] for f in (snm["monte_carlo"].get("family_mismatch") or [])}
    bad = [e["corner_id"] for e in snm["samples"] + wr["samples"] if "error" in e]
    asym = [min(e["hold_asym_v"], e["read_asym_v"]) for e in snm["samples"] if "error" not in e]
    cid = dw["corners"][0]["corner_id"]
    det_now, det_old = dw["corners"][0].get("write_margin_v"), det_ref.get(cid)
    equiv = det_old is not None and det_now == det_old
    if fam.get("mosfet") is not True: problems.append(f"{t}: klt does not report MOS mismatch active")
    if not asym or min(asym) <= 0: problems.append(f"{t}: identical instances do not differ in every sample")
    if bad: problems.append(f"{t}: {len(bad)} errored samples")
    if not equiv: problems.append(f"{t}: single-cell write bench {det_now} != 45-corner record {det_old}")
    meas = {}
    for m in y["measurements"]:
        yy, cap, ss = m["yield"]["empirical"], m["capability"], m["sample_size"]
        vals = [v for v in next(s for s in L(f"yield/set_{t}.json")["measurements"] if s["name"] == m["name"])["samples"]]
        meas[m["name"]] = {"n": m["n"], "failed_unmeasurable": m["failed_unmeasurable"], "errored": m["errored"],
                           "mean": m["distribution"]["mean"], "stddev": m["distribution"]["stddev"],
                           "min": min(vals) if vals else None,
                           "samples_not_strictly_positive": sum(1 for v in vals if not v > 0) + m["failed_unmeasurable"],
                           "cpk": cap["cpk"], "cpk_ci": cap["cpk_confidence_interval"],
                           "sigma_to_spec": cap["sigma_to_spec"], "sigma_to_spec_ci": cap["sigma_to_spec_confidence_interval"],
                           "empirical_yield": yy["estimate"], "empirical_yield_ci": yy["confidence_interval"],
                           "sample_size_verdict": ss["verdict"], "required_n": ss.get("required_n")}
    out_pts.append({"point": " ".join(p), "tag": t, "mosfet_mismatch_active": fam.get("mosfet"),
                    "min_instance_asymmetry_v": min(asym) if asym else None,
                    "deterministic_write_margin_v": det_now, "deterministic_record_write_margin_v": det_old,
                    "measurements": meas})
negs = []
for p in negpoints:
    t = tag(p)
    ref = [e["read_snm_v"] for e in L(f"samples/snm_{t}.json")["samples"] if e.get("read_snm_v") is not None]
    neg = [e["read_snm_v"] for e in L(f"samples/negctl_snm_{t}.json")["samples"] if e.get("read_snm_v") is not None]
    mean = lambda v: sum(v) / len(v)
    detected = open(f"{rec}/negctl/result_{t}.txt").read().strip() == "detected"
    negs.append({"point": " ".join(p), "reference_read_snm_mean_v": mean(ref), "negctl_read_snm_mean_v": mean(neg),
                 "negctl_read_snm_max_v": max(neg), "reference_read_snm_min_v": min(ref), "detected": detected})
    if not detected: problems.append(f"{t}: negative control not detected")
determinism = open(f"{rec}/determinism.txt").read().strip() == "identical"
if not determinism: problems.append("same seed did not reproduce the same samples")
remote = env.get("remote", {})
out = {
  "stamp": stamp, "kind": "simulated", "pdk_release_tag": pdktag,
  "cell": "6T, pull-down sg13_lv_nmos 300n/130n, pull-up sg13_lv_pmos 150n/130n, access sg13_lv_nmos 300n/130n (spec/bitcell-decision.md evidence 1)",
  "engine": {"version_banner": env.get("engine_build", {}).get("version_banner"), "runner_klt_version": remote.get("runner_klt_version")},
  "monte_carlo": {"vary": "mismatch", "seed": seed, "n_per_corner_point": n,
                  "models": "cornerMOSlv.lib mos_<corner>_mismatch sections",
                  "drawn_per_device": "agauss() per instance: w, l (dw/dl), delvto (Vth, Pelgrom 1/sqrt(m*l*w)), factuo (mobility, 1/sqrt(m*l*w)); no process (global) variation is drawn, the process corner is the named section",
                  "limit": "strictly positive (lower limit 0 V, exclusive); no target_yield"},
  "corner_coverage": {"sampled": [" ".join(p) for p in points],
                      "not_sampled": "the other corner points of the 45-corner matrix (records/*/ holds their deterministic result; this MC supplements it, never replaces it)"},
  "write_margin_note": "write margin is quantised to the 25 mV bit-line grid (spec/ write-margin definition, issue #71); the distribution is a 25 mV histogram",
  "points": out_pts, "negative_control": negs,
  "same_seed_reproduces_samples": determinism,
  "problems": problems,
}
json.dump(out, open(f"{rec}/record.json", "w"), indent=2); open(f"{rec}/record.json", "a").write("\n")
print(json.dumps(out, indent=2))
sys.exit(0 if not problems and not gates else 1)
PY

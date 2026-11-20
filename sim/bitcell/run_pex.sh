#!/usr/bin/env bash
# run_pex.sh -- bitcell post-layout re-run (issue #228, T1 item 7 first
# increment): schematic-vs-extracted read SNM, hold SNM and write margin via
# `klt pex --measure-command`, on the LVS-matched 6T bitcell layout.
#
# What runs (every margin value is labelled `simulated`; nothing here is a
# spec value):
#   1. PDK-free `klt pex --extract-only` at the CI klt pin: the digest
#      layout/verify.sh step 11 re-checks is recorded from this run.
#   2. PDK-bound `klt pex --measure-command` (batch backend, fleet only):
#      extraction with parasitics on layout/bitcell/sg13g2_sram_bitcell_6t.gds,
#      then sim/bitcell/measure_pex.py measures BOTH legs -- the schematic
#      design/bitcell/bitcell.spice and the extracted netlist -- with the
#      existing benches and bitcell_post.py reducers, at the corner that
#      bounds each margin in the schematic grid plus the typical point.
#   3. record.json: the delta rows, body_bias / extraction.model /
#      model_mismatch quotes, both extraction digests, the extracted R/C
#      inventory, batch job ids, and a cross-check of the schematic leg
#      against the 2026-10-28 schematic record (a pin swap would show up
#      there, not as a small post-layout delta).
#
# Backend policy: batch fleet only (`--backend batch`, `--wait-for-capacity
# 600` on every fleet submit). A failed submit exits non-zero; nothing falls
# back to a local loop (sim/README.md).
#
# Usage (after sim/README.md "Cold start" step 1):
#   sim/bitcell/run_pex.sh
# Writes a new, never-overwritten record under sim/bitcell/records/<UTC>/.
# Exit 0 iff every step ran and the cross-check held. A FAILING post-layout
# margin is a recorded result (a decision-record finding, per issue #228),
# not a script error; an errored delta row or a fleet failure is an error.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${HERE}/../harness/common/setup.sh"
sim_setup

# The CI klt pin (KLT_VERSION in .github/workflows/ci.yml): the committed
# digests and envelope must be reproducible at it, so never the host `klt`
# (same rule as attest/mint.sh; the host tool is a dev build).
KLT_VERSION="$(sed -n 's/.*KLT_VERSION: "\([^"]*\)".*/\1/p' "${REPO}/.github/workflows/ci.yml" | head -1)"
: "${KLT_VERSION:?run_pex.sh: no KLT_VERSION pin found in .github/workflows/ci.yml}"
KLT=(uvx --from "klayout-tools==${KLT_VERSION}" klt)
export PEX_KLT="uvx --from klayout-tools==${KLT_VERSION} klt"

GDS="${REPO}/layout/bitcell/sg13g2_sram_bitcell_6t.gds"
REF="${REPO}/design/bitcell/bitcell.spice"

new_record "${HERE}/records" reports curves measure

# --- 1. PDK-free extract-only: the digest verify.sh re-checks ----------------
rc=0
"${KLT[@]}" pex "$GDS" --deck sg13g2 --extract-only --reference-netlist "$REF" \
  -o "$WORK/free.spice" --envelope-out "$WORK/free-envelope.json" \
  --outdir "$WORK/free-out" --format json >/dev/null 2> "$WORK/free.stderr" || rc=$?
# extract-only measures nothing: exit 4 with status not_checked is the result.
[[ "$rc" -eq 4 ]] || { echo "run_pex.sh: PDK-free extract-only exited $rc (want 4)" >&2; tail -5 "$WORK/free.stderr" >&2; exit 6; }
python3 -I - "$WORK/free-envelope.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["status"] == "not_checked", d["status"]
assert d["measurement"]["mode"] == "extract-only", d["measurement"]["mode"]
PY

# --- 2. measured PDK-bound run (batch fleet) ----------------------------------
# Run from the repo root with a repo-relative measure-command: the envelope
# records the argv verbatim (measurement.command), and a home-shaped absolute
# path there would leak the invoking checkout into committed evidence
# (klt env-provenance scan flags it; same rule layout/verify.sh step 10
# applies to layout/reports/).
cd "${REPO}"
rc=0
"${KLT[@]}" pex "$GDS" --deck sg13g2 --pdk ihp-sg13g2 --pdk-root "${PDK_ROOT}" \
  --backend batch --wait-for-capacity 600 --measure-timeout-s 7200 \
  --measure-command "python3 -I sim/bitcell/measure_pex.py" \
  --reference-netlist "$REF" \
  -o "$WORK/extracted.spice" --envelope-out "${REC}/pex-envelope.json" \
  --outdir "$WORK/pex-out" --format json > "$WORK/pex.stdout" 2> "${REC}/reports/pex.stderr" || rc=$?
# 0 = every delta row passed, 3 = at least one row failed its limits: both are
# measured results. 4 = errored rows / nothing compared; 1 = the run itself
# failed (extraction, fleet, or the measurement command).
if [[ "$rc" -ne 0 && "$rc" -ne 3 ]]; then
  echo "run_pex.sh: klt pex exited $rc (envelope kept in the record for diagnosis)" >&2
  tail -5 "${REC}/reports/pex.stderr" >&2
  exit 5
fi

# --- 3. collect, cross-check, record ------------------------------------------
cp "$WORK/free.spice" "${REC}/extract-pdk-free.spice"
cp "$WORK/extracted.spice" "${REC}/extract-parasitic-pdk.spice"
for side in schematic extracted; do
  d="${WORK}/pex-out/measure/${side}/stage-${side}"
  cp "${d}/measurements-${side}.json" "${REC}/measure/"
  for f in "${d}/curves"/*.csv; do cp "$f" "${REC}/curves/${side}-$(basename "$f")"; done
  cp "${d}/report-snm.json.gz" "${d}/report-write.json.gz" "${REC}/reports/" \
    && mv "${REC}/reports/report-snm.json.gz" "${REC}/reports/${side}-snm.json.gz" \
    && mv "${REC}/reports/report-write.json.gz" "${REC}/reports/${side}-write.json.gz"
  cp "${d}/dut.spice" "${d}/bench_snm.cir" "${d}/bench_write.cir" "${REC}/measure/" \
    && mv "${REC}/measure/dut.spice" "${REC}/measure/${side}-dut.spice" \
    && mv "${REC}/measure/bench_snm.cir" "${REC}/measure/${side}-bench_snm.cir" \
    && mv "${REC}/measure/bench_write.cir" "${REC}/measure/${side}-bench_write.cir"
done

PDKTAG="$(pdk_release_tag)"
python3 -I - "${REC}" "${STAMP}" "${PDKTAG}" "${KLT_VERSION}" <<'PY'
import hashlib, json, re, sys

rec, stamp, pdktag, klt_pin = sys.argv[1:5]
L = lambda n: json.load(open(f"{rec}/{n}"))
env = L("pex-envelope.json")
sch = L("measure/measurements-schematic.json")
ext = L("measure/measurements-extracted.json")

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

free_sha = sha(f"{rec}/extract-pdk-free.spice")
pdk_sha = sha(f"{rec}/extract-parasitic-pdk.spice")
net_sha = env["extraction"]["netlist_sha256"]
assert pdk_sha == net_sha, f"extracted netlist digest {pdk_sha} != envelope {net_sha}"

# Cross-check the schematic leg against the 2026-10-28 schematic record at the
# typical point: identical benches/models must reproduce it closely; a pin
# swap in the staged deck collapses read SNM, it does not perturb it.
HIST = {"hold_snm": 0.48583337839088236, "read_snm": 0.21317047273854042,
        "write_margin": 0.4}
TYP = "mos_tt/1.200V/27C"
vals = {m["name"]: m["value"] for m in
        next(c for c in sch["corners"] if c["corner_id"] == TYP)["measurements"]}
cross = {k: {"recorded": HIST[k], "pex_schematic_leg": vals.get(k),
             "abs_diff_v": None if vals.get(k) is None else round(abs(vals[k] - HIST[k]), 9)}
         for k in HIST}
for k, c in cross.items():
    if c["pex_schematic_leg"] is None or c["abs_diff_v"] > 0.010:
        sys.exit(f"FAIL: schematic leg {k} at {TYP} is {c['pex_schematic_leg']}, "
                 f"2026-10-28 record has {c['recorded']} -- staged pins suspect")

# Extracted R/C inventory, per net, from the committed extraction. Only the
# top subckt's pin nets: the vsubs DC tie (R vsubs 0 1e+12) is deck plumbing,
# not a signal-net parasitic.
rc_text = open(f"{rec}/extract-parasitic-pdk.spice").read()
top_pins = set(re.search(r"^\.SUBCKT\s+\S+\s+(.+)$", rc_text, re.M).group(1).split())
r_ohms, terms = {}, {}
for net, r in re.findall(r"^R\S+\s+\S+\s+(\S+)\s+([0-9.eE+-]+)\s*$", rc_text, re.M):
    if net in top_pins:
        r_ohms[net] = r_ohms.get(net, 0.0) + float(r)
        terms[net] = terms.get(net, 0) + 1
c_ff = {net: float(c) * 1e15 for net, c in
        re.findall(r"^C\S+\s+(\S+)\s+vsubs\s+([0-9.eE+-]+)\s*$", rc_text, re.M)
        if net in top_pins}
parasitics = {net: {"terminals": terms[net], "star_r_ohms_total": round(r_ohms[net], 6),
                    "c_to_vsubs_ff": round(c_ff[net], 6)} for net in sorted(r_ohms)}

def side_meta(doc):
    b = doc["provenance"]["batches"]
    return {"snm": b["snm"]["batch_job_id"], "write": b["write"]["batch_job_id"]}

out = {
  "stamp": stamp, "kind": "pex", "pdk_release_tag": pdktag,
  "issue": "2AMLogic/sg13g2-sram#228 (T1 item 7, first increment: the bitcell)",
  "what": "schematic-vs-extracted read SNM, hold SNM and write margin of the LVS-matched 6T bitcell "
          "(layout/bitcell/sg13g2_sram_bitcell_6t.gds), klt pex --measure-command, batch fleet",
  "corners": {"points": sch["provenance"]["corner_points"],
              "why": "the corner bounding each margin in the schematic 45-corner grid "
                     "(sim/bitcell/records/20261028T143337Z) plus the typical point, kept "
                     "separate from the grid's 25 C middle as run_bitcell.sh does"},
  "tool": {"klt_pin": klt_pin, "deck": "sg13g2", "pdk_variant": "ihp-sg13g2",
           "parasitic_settings": "deck defaults (no --critical-net, no --distributed-rc, "
                                 "no --mom-rlc-*, lumped star R, C to vsubs)"},
  "envelope": {"status": env["status"], "passed": env["passed"], "failed": env["failed"],
               "errored": env["errored"], "corner_count": env["corner_count"],
               "measurement_mode": env["measurement"]["mode"],
               "path": "pex-envelope.json"},
  "extraction_digests": {
      "pdk_free_spice_sha256": free_sha,
      "pdk_bound_spice_sha256": pdk_sha,
      "envelope_netlist_sha256": net_sha,
      "recheck": "layout/verify.sh step 11 re-runs the PDK-free extraction and compares "
                 "against pdk_free_spice_sha256 (CI has no PDK install)",
  },
  "disclosures": {
      "body_bias_status": env["body_bias"]["status"],
      "unbiased_nets": env["body_bias"]["unbiased_nets"],
      "extraction_model": env["extraction"]["model"],
      "model_mismatch": env["model_mismatch"],
      "device_classes": env["extraction"]["device_classes"],
      "unsupported_devices": env["extraction"]["unsupported_devices"],
      "parasitic_integrity": {k: v for k, v in env["extraction"]["parasitic_integrity"].items()
                              if k != "nets"},
  },
  "parasitics_per_net": parasitics,
  "batch_job_ids": {"schematic": side_meta(sch), "extracted": side_meta(ext)},
  "schematic_leg_cross_check_vs_20261028T143337Z": cross,
  "delta_rows": [{"spec_row": d["spec_row"], "corner_id": d["corner_id"],
                  "schematic_value": d["schematic_value"],
                  "extracted_value": d["extracted_value"],
                  "delta_pct": d["delta_pct"], "status": d["status"]}
                 for d in env["delta"]],
  "measurement_docs": {"schematic": "measure/measurements-schematic.json",
                       "extracted": "measure/measurements-extracted.json"},
  "curves": sorted(p.name for p in __import__("pathlib").Path(rec, "curves").glob("*.csv")),
  "not_established": ["the macro-level PEX run (after #30; ROADMAP.md)",
                      "Monte Carlo (#68)", "write flip time (spec/write-pulse-width-decision.md)",
                      "write-margin shifts below the 25 mV bin, and any DC-vs-geometry split "
                      "of a delta row: this data cannot distinguish them (see README.md)"],
}
json.dump(out, open(f"{rec}/record.json", "w"), indent=2)
open(f"{rec}/record.json", "a").write("\n")
print(json.dumps(out, indent=2))
PY
echo "run_pex.sh: record ${REC} (envelope status: $(python3 -I -c "import json;print(json.load(open('${REC}/pex-envelope.json'))['status'])"))"

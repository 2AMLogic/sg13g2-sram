#!/usr/bin/env bash
# run_smoke.sh -- SG13G2 PDK/OSDI smoke simulation (T1 item 9).
#
# For each of four standard IHP devices (sg13_lv_nmos, sg13_lv_pmos,
# sg13_hv_nmos, sg13_hv_pmos): one DC operating point and one Id-Vgs sweep,
# typical MOS corner (mos_tt), 27 C, single corner, local `ngspice -b` per
# device (four runs, no grid). Exits non-zero if any device fails to converge.
# Biases and geometries here exercise the toolchain only; they are NOT spec
# values (no bitcell device, supply or swing is chosen).
#
# Usage (after build-osdi.sh; see sim/README.md "Cold start"):
#   sim/pdk-smoke/run_smoke.sh
# Writes a new, never-overwritten record under sim/pdk-smoke/records/<UTC>/.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${HERE}/.." && pwd)"
# shellcheck source=/dev/null
source "${SIM_DIR}/harness/common/env.sh"
: "${PDK_ROOT:?run_smoke.sh: no PDK install resolved; see sim/README.md}"
MODELS="${PDK_ROOT}/${PDK}/libs.tech/ngspice/models"
OSDI_DIR="${PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi"
for m in psp103 psp103_nqs r3_cmc mosvar; do
  [[ -f "${OSDI_DIR}/${m}.osdi" ]] || { echo "run_smoke.sh: ${m}.osdi missing; run build-osdi.sh" >&2; exit 3; }
done
command -v ngspice >/dev/null || { echo "run_smoke.sh: ngspice not on PATH" >&2; exit 3; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REC="${HERE}/records/${STAMP}"
[[ -e "${REC}" ]] && { echo "run_smoke.sh: ${REC} exists (records are append-only)" >&2; exit 4; }
mkdir -p "${REC}/netlists" "${REC}/logs"
WORK="$(mktemp -d)"; trap 'rm -rf "${WORK}"' EXIT

# name | corner lib | W | L | polarity sign | Vds | Vgs max
DEVICES=(
  "sg13_lv_nmos|cornerMOSlv.lib|1u|0.13u|1|0.6|1.2"
  "sg13_lv_pmos|cornerMOSlv.lib|1u|0.13u|-1|0.6|1.2"
  "sg13_hv_nmos|cornerMOShv.lib|1u|0.45u|1|1.65|3.3"
  "sg13_hv_pmos|cornerMOShv.lib|1u|0.45u|-1|1.65|3.3"
)
STEP_DIV=33  # sweep points = STEP_DIV + 1

for d in "${DEVICES[@]}"; do
  IFS='|' read -r name lib w l sgn vds vgmax <<<"${d}"
  vd=$(python3 -I -c "print(${sgn}*${vds})"); vg=$(python3 -I -c "print(${sgn}*${vgmax}/2)")
  vgend=$(python3 -I -c "print(${sgn}*${vgmax})"); step=$(python3 -I -c "print(${sgn}*${vgmax}/${STEP_DIV})")
  deck="${WORK}/${name}.cir"
  cat > "${deck}" <<DECK
* ${name} smoke: DC op + Id-Vgs, mos_tt, 27 C. Toolchain check only, not a spec bias.
.lib "${MODELS}/${lib}" mos_tt
.temp 27
Vd d 0 dc ${vd}
Vg g 0 dc ${vg}
XM d g 0 0 ${name} w=${w} l=${l} ng=1 m=1
.control
pre_osdi ${OSDI_DIR}/psp103.osdi
pre_osdi ${OSDI_DIR}/psp103_nqs.osdi
pre_osdi ${OSDI_DIR}/r3_cmc.osdi
pre_osdi ${OSDI_DIR}/mosvar.osdi
op
print i(Vd)
dc Vg 0 ${vgend} ${step}
wrdata ${WORK}/${name}.sweep.txt i(Vd)
.endc
.end
DECK
  # Committed deck: host-specific PDK_ROOT replaced by a literal placeholder.
  sed "s|${PDK_ROOT}|\${PDK_ROOT}|g" "${deck}" > "${REC}/netlists/${name}.cir"
  set +e
  ngspice -b "${deck}" > "${REC}/logs/${name}.log" 2>&1
  echo "$?" > "${WORK}/${name}.rc"
  set -e
  cp "${WORK}/${name}.sweep.txt" "${REC}/logs/${name}.sweep.txt" 2>/dev/null || true
  sed -i "s|${PDK_ROOT}|\${PDK_ROOT}|g" "${REC}/logs/${name}.log"
done

OV="$(sed -n 's/^OPENVAF_TAG="\([^"]*\)".*/\1/p' "${SIM_DIR}/harness/common/tools/build-osdi.sh" | head -1)"
PDKTAG="$(grep -o '"release_tag": *"[^"]*"' "${SIM_DIR}/pdk.json" | head -1 | cut -d'"' -f4)"
NGV="$(ngspice --version 2>&1 | grep -m1 -o 'ngspice-[0-9.]*')"

python3 -I - "${REC}" "${WORK}" "${PDKTAG}" "${OV}" "${NGV}" "${STEP_DIV}" "${DEVICES[@]}" <<'PY'
import json, math, os, sys
rec, work, pdktag, ov, ngv, div = sys.argv[1:7]
div = int(div)
devs = [d.split("|") for d in sys.argv[7:]]
out = {"stamp": os.path.basename(rec), "pdk_release_tag": pdktag,
       "openvaf_r_version": ov, "ngspice_version": ngv,
       "corner": "mos_tt", "temp_c": 27, "devices": {}}
ok = True
for name, lib, w, l, sgn, vds, vgmax in devs:
    rc = int(open(f"{work}/{name}.rc").read())
    log = open(f"{rec}/logs/{name}.log", errors="replace").read()
    op_id = None
    for line in log.splitlines():
        if line.lower().startswith("i(vd)"):
            op_id = float(line.split("=")[1])
    rows = []
    try:
        for line in open(f"{work}/{name}.sweep.txt"):
            a = line.split()
            rows.append((float(a[0]), float(a[1])))
    except OSError:
        pass
    bad = ("no convergence" in log.lower() or "singular matrix" in log.lower()
           or "couldn't be loaded" in log.lower() or "unknown model" in log.lower())
    mag = [abs(r[1]) for r in rows]
    conv = (rc == 0 and not bad and op_id is not None and math.isfinite(op_id)
            and len(rows) == div + 1 and all(math.isfinite(x) for x in mag)
            and mag[-1] > 1e-6 and mag[-1] > 100 * max(mag[0], 1e-15))
    ok &= conv
    out["devices"][name] = {"lib": lib, "w": w, "l": l, "converged": conv,
        "ngspice_rc": rc, "op_id_a": op_id, "sweep_points": len(rows),
        "id_at_vgs_max_a": rows[-1][1] if rows else None,
        "id_at_vgs_0_a": rows[0][1] if rows else None}
out["all_converged"] = ok
json.dump(out, open(f"{rec}/record.json", "w"), indent=2)
open(f"{rec}/record.json", "a").write("\n")
print(json.dumps(out, indent=2))
sys.exit(0 if ok else 1)
PY

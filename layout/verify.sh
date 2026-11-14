#!/usr/bin/env bash
# Regenerate the bitcell layout and re-run its cell-level checks (DRC, extract,
# LVS) -- a pre-check, not the macro signoff flow. Run from anywhere:
#
#     ./layout/verify.sh
#
# Needs klt (>= 0.8.0, sg13g2 deck) and uv on PATH for steps 1-9. Step 10 needs klt >= 0.9.0,
# which first carries `array-check`; it does not use the host klt at all but pins
# klayout-tools==0.9.1 through `uvx`, matching layout/reports/array-check-macro.json. Nothing
# here writes into sim/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PY="uv run --with klayout python3"
CELL=layout/bitcell/sg13g2_sram_bitcell_6t.gds
TILE=layout/bitcell/sg13g2_sram_bitcell_tile2x2.gds
REF=design/bitcell/bitcell.spice

hr() { printf '\n=== %s ===\n' "$1"; }

hr "1. regenerate (the committed GDS must not change)"
$PY layout/bitcell/generate.py
if git diff --quiet -- "$CELL" "$TILE"; then
  echo "PASS: regenerated GDS is byte-identical to the committed GDS"
else
  echo "FAIL: regenerated GDS differs from the committed GDS"; exit 1
fi

hr "2. DRC: bitcell and 2x2 mirror tile (klt drc --deck sg13g2)"
klt drc --deck sg13g2 "$CELL"
klt drc --deck sg13g2 "$TILE"

hr "3. extract + LVS: bitcell vs $REF"
klt extract --deck sg13g2 "$CELL" -o "$WORK/bitcell.spice"
klt lvs "{\"layout\":{\"netlist\":\"$WORK/bitcell.spice\",\"top\":\"sg13g2_sram_bitcell_6t\"},\
\"reference\":{\"netlist\":\"$ROOT/$REF\",\"top\":\"bitcell\",\"form\":\"subckt-call\"}}"

hr "4. extract + LVS: 2x2 tile vs four bitcell instances"
klt extract --deck sg13g2 "$TILE" -o "$WORK/tile.spice"
{ grep -v '^\*' "$REF"; cat <<'EOF'
.subckt tile2x2 BL0 BLB0 BL1 BLB1 WL0 WL1 VDD VSS
Xc00 BL0 BLB0 WL0 VDD VSS q00 qb00 bitcell
Xc10 BL1 BLB1 WL0 VDD VSS q10 qb10 bitcell
Xc01 BL0 BLB0 WL1 VDD VSS q01 qb01 bitcell
Xc11 BL1 BLB1 WL1 VDD VSS q11 qb11 bitcell
.ends
EOF
} > "$WORK/tile_ref.spice"
klt lvs "{\"layout\":{\"netlist\":\"$WORK/tile.spice\",\"top\":\"sg13g2_sram_bitcell_tile2x2\"},\
\"reference\":{\"netlist\":\"$WORK/tile_ref.spice\",\"top\":\"tile2x2\",\"form\":\"subckt-call\"},\
\"options\":{\"flatten_reference\":true}}"

hr "5. generator tests (determinism, W/L read-back, LVS teeth)"
(cd layout/bitcell && uv run --with pytest --with klayout pytest -q test_bitcell.py)

hr "6. macro: regenerate (the committed GDS, socket and LEF must not change)"
D=layout/sram_256x32
cp $D/macro.gds "$WORK/macro.gds.committed"
cp $D/macro.socket.json "$WORK/macro.socket.json.committed"
$PY $D/generate.py
klt lef-abstract $D/macro.gds --socket $D/macro.socket.json --macro-name macro \
  --cell-library sg13g2_stdcell --pdk ihp-sg13g2 --obs-mode coarse -o "$WORK/macro.lef" > /dev/null
if cmp -s "$WORK/macro.gds.committed" $D/macro.gds && cmp -s "$WORK/macro.socket.json.committed" $D/macro.socket.json \
   && cmp -s "$WORK/macro.lef" $D/macro.lef; then
  echo "PASS: regenerated macro GDS, socket and LEF are identical to the committed files"
else
  echo "FAIL: regenerated macro outputs differ from the committed files"; exit 1
fi

hr "7. macro: socket-check and generator tests (8192 bitcells, LEF pins = netlist ports)"
klt socket-check --socket $D/macro.socket.json $D/macro.gds
(cd $D && uv run --with pytest --with klayout pytest -q test_macro.py)

hr "8. macro: DRC of the full array (klt drc --deck sg13g2; coverage gaps are in the report)"
klt drc --deck sg13g2 --top macro $D/macro.gds
klt drc --check layout/reports/drc-macro.json

hr "9. macro: the latest (decoder-net) record matches the committed layout; every tie and riser reaches a rail; no rail below Metal4 in the wordline gap"
python3 - <<'PYEOF'
import hashlib, json, sys
rec = json.load(open("layout/reports/macro-record-decoder.json"))
for key in ("gds", "lef", "socket"):
    for path, want in rec[key].items():
        got = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if got != want:
            sys.exit(f"FAIL: {path} differs from macro-record-decoder.json")
c = rec["rails_connectivity"]
ok = (c["ties_on_own_rail"] == c["ties_expected"] and c["ties_floating"] == 0 and c["ties_on_other_rail"] == 0
      and c["vdd_vss_short_polygons"] == 0
      and all(v["on_rail"] == v["expected"] and v["on_other_rail"] == 0 for v in c["bitcell_risers"].values()))
if not ok:
    sys.exit("FAIL: macro-record-decoder.json reports a floating tie, a stray rail or a short")
if rec["rails_vs_wordline_gap"]["total"] != 0:
    sys.exit("FAIL: macro-record-decoder.json reports a rail shape below Metal4 in the wordline gap")
print(f"PASS: record matches the files; {c['ties_on_own_rail']}/{c['ties_expected']} ties and all bitcell risers on their rail; wordline gap clear")
PYEOF

hr "10. macro: array regularity (klt array-check; pinned klt 0.9.1 -- the host/signoff 0.8.0 lacks the verb)"
AC=layout/reports/array-check-macro.json
ACK=(uvx --from klayout-tools==0.9.1 klt)
"${ACK[@]}" clip $D/macro.gds --cell bl_pair -o "$WORK/bl_pair.gds" > /dev/null
# The two abutment configurations are assertions: a non-clean status fails the step. Their
# tolerances are the measured shared-edge overlap of mirror abutment, not slack -- read the
# tolerance_rationale in the record before touching them.
for spec in "$D/macro.gds|bit_slice|5.74|32|x|0.48" "$WORK/bl_pair.gds|bitcell|3.605|128|y|0.27"; do
  IFS='|' read -r f cell pitch count dir tol <<<"$spec"
  # array-check exits 3 on `violated` -- a successful run with findings. Capture it rather than
  # letting `set -e` abort the step before the diagnostic below prints.
  rc=0
  "${ACK[@]}" array-check "$f" --cell "$cell" --pitch "$pitch" --count "$count" \
    --direction "$dir" --tolerance "$tol" --format json > "$WORK/abutment.json" || rc=$?
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 3 ]; then
    echo "FAIL: klt array-check exited $rc on $cell along $dir"; exit "$rc"
  fi
  st="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$WORK/abutment.json")"
  if [ "$st" = "clean" ]; then
    echo "PASS: abutment $cell along $dir at pitch $pitch x $count (tolerance $tol) is clean"
  else
    echo "FAIL: abutment $cell along $dir reports status '$st', expected clean"; exit 1
  fi
done
# The symmetry run is a *characterized* result, not a pass: 8 residuals at the finite-array end and
# at seam 0, both documented. Assert the recorded count and y bands so a change that breaks interior
# symmetry fails here instead of being absorbed. Do NOT raise --tolerance to make this report clean.
"${ACK[@]}" array-check "$WORK/bl_pair.gds" --cell bl_pair --translate '0,7.21' \
  --layers '[[1,0],[5,0],[8,0],[10,0]]' --format json > "$WORK/symmetry.json" || true
python3 -I - "$WORK/symmetry.json" "$AC" <<'SYMEOF'
import json, sys
got = json.load(open(sys.argv[1]))
rec = json.load(open(sys.argv[2]))
inv = next(i for i in rec["invocations"] if i["name"] == "column-translation-symmetry")
want = inv["characterization"]
bands = [tuple(b) for b in want["y_bands_um"]]
if got["violation_count"] != want["residual_count"]:
    sys.exit(f"FAIL: {got['violation_count']} symmetry residuals, record says {want['residual_count']}"
             " -- interior symmetry may have changed; mint a new record deliberately,"
             " do not retune tolerance")
stray = [v["bbox"] for v in got["violations"]
         if not any(lo - 1e-6 <= v["bbox"]["bottom"] and v["bbox"]["top"] <= hi + 1e-6
                    for lo, hi in bands)]
if stray:
    sys.exit(f"FAIL: {len(stray)} symmetry residual(s) outside the recorded y bands {bands}: {stray}")
print(f"PASS: {got['violation_count']} symmetry residuals, all within the recorded y bands {bands}"
      " (finite-array end + seam 0)")
SYMEOF
# scan exits 3 when it finds a home-directory-shaped absolute path; report that rather than
# letting `set -e` abort the step silently.
if "${ACK[@]}" env-provenance scan "$AC" > /dev/null; then
  echo "PASS: no home-directory-shaped absolute path in $AC"
else
  echo "FAIL: $AC carries a home-directory-shaped absolute path:"
  "${ACK[@]}" env-provenance scan "$AC" || true
  exit 1
fi
python3 -I - "$AC" <<'HASHEOF'
import hashlib, json, sys
rec = json.load(open(sys.argv[1]))
for path, want in rec["provenance"]["inputs"].items():
    if path.startswith("(derived)"):
        continue
    got = "sha256:" + hashlib.sha256(open(path, "rb").read()).hexdigest()
    if got != want:
        sys.exit(f"FAIL: {path} differs from array-check-macro.json"
                 " -- the array changed, so mint a new record (records are append-only)")
print("PASS: array-check-macro.json pins the committed GDS inputs")
HASHEOF

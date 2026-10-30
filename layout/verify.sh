#!/usr/bin/env bash
# Regenerate the bitcell layout and re-run its cell-level checks (DRC, extract,
# LVS) -- a pre-check, not the macro signoff flow. Run from anywhere:
#
#     ./layout/verify.sh
#
# Needs klt (>= 0.8.0, sg13g2 deck) and uv on PATH. Nothing here writes into sim/.
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

hr "9. macro: the leaf-net record matches the committed layout; every tie and riser reaches a rail; no rail below Metal4 in the wordline gap"
python3 - <<'PYEOF'
import hashlib, json, sys
rec = json.load(open("layout/reports/macro-record-leafnets.json"))
for key in ("gds", "lef", "socket"):
    for path, want in rec[key].items():
        got = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if got != want:
            sys.exit(f"FAIL: {path} differs from macro-record-leafnets.json")
c = rec["rails_connectivity"]
ok = (c["ties_on_own_rail"] == c["ties_expected"] and c["ties_floating"] == 0 and c["ties_on_other_rail"] == 0
      and c["vdd_vss_short_polygons"] == 0
      and all(v["on_rail"] == v["expected"] and v["on_other_rail"] == 0 for v in c["bitcell_risers"].values()))
if not ok:
    sys.exit("FAIL: macro-record-leafnets.json reports a floating tie, a stray rail or a short")
if rec["rails_vs_wordline_gap"]["total"] != 0:
    sys.exit("FAIL: macro-record-leafnets.json reports a rail shape below Metal4 in the wordline gap")
print(f"PASS: record matches the files; {c['ties_on_own_rail']}/{c['ties_expected']} ties and all bitcell risers on their rail; wordline gap clear")
PYEOF

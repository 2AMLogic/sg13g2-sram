#!/usr/bin/env bash
# Mint the bitcell evidence reports in this directory (issue #27). Run from
# anywhere:   ./layout/reports/generate.sh
#
# Reports are append-only evidence: do not edit one to change a result. A re-run
# after a layout or klt change is a new result -- commit it as such and say why
# in the commit message (git history is the trail).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
OUT=layout/reports
CELL=layout/bitcell/sg13g2_sram_bitcell_6t.gds
TILE=layout/bitcell/sg13g2_sram_bitcell_tile2x2.gds
REF=design/bitcell/bitcell.spice
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

klt drc --deck sg13g2 --format json "$CELL" > "$OUT/drc-bitcell.json"
klt drc --deck sg13g2 --format json "$TILE" > "$OUT/drc-tile2x2.json"

klt extract --deck sg13g2 --format json "$CELL" -o "$WORK/bitcell.spice" > "$WORK/x.json"
cp "$WORK/bitcell.spice" "$OUT/bitcell-extracted.spice"
python3 - "$WORK/x.json" "$OUT/extract-bitcell.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
d["netlist_path"] = "layout/reports/bitcell-extracted.spice"  # a temp dir at generation time
json.dump(d, open(sys.argv[2], "w"), indent=2); open(sys.argv[2], "a").write("\n")
EOF
klt lvs "{\"layout\":{\"netlist\":\"$ROOT/$OUT/bitcell-extracted.spice\",\"top\":\"sg13g2_sram_bitcell_6t\"},\
\"reference\":{\"netlist\":\"$ROOT/$REF\",\"top\":\"bitcell\",\"form\":\"subckt-call\"}}" \
  --format json > "$OUT/lvs-bitcell.json"

klt extract --deck sg13g2 --format json "$TILE" -o "$OUT/tile2x2-extracted.spice" > /dev/null
{ grep -v '^\*' "$REF"; cat <<'EOF'
.subckt tile2x2 BL0 BLB0 BL1 BLB1 WL0 WL1 VDD VSS
Xc00 BL0 BLB0 WL0 VDD VSS q00 qb00 bitcell
Xc10 BL1 BLB1 WL0 VDD VSS q10 qb10 bitcell
Xc01 BL0 BLB0 WL1 VDD VSS q01 qb01 bitcell
Xc11 BL1 BLB1 WL1 VDD VSS q11 qb11 bitcell
.ends
EOF
} > "$OUT/tile2x2-reference.spice"
klt lvs "{\"layout\":{\"netlist\":\"$ROOT/$OUT/tile2x2-extracted.spice\",\"top\":\"sg13g2_sram_bitcell_tile2x2\"},\
\"reference\":{\"netlist\":\"$ROOT/$OUT/tile2x2-reference.spice\",\"top\":\"tile2x2\",\"form\":\"subckt-call\"},\
\"options\":{\"flatten_reference\":true}}" --format json > "$OUT/lvs-tile2x2.json"

python3 - "$CELL" "$TILE" > "$OUT/bitcell-record.json" <<'EOF'
import hashlib, json, subprocess, sys
cell, tile = sys.argv[1:3]
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
pitch = subprocess.run(
    ["uv", "run", "--with", "klayout", "python3", "-c",
     "import sys; sys.path.insert(0,'layout/bitcell'); import generate as g; print(g.W_CELL, g.H_CELL)"],
    capture_output=True, text=True, check=True).stdout.split()
wc, hc = float(pitch[0]), float(pitch[1])
deck = json.loads(subprocess.run(["klt", "deck", "info", "--deck", "sg13g2", "--format", "json"],
                                 capture_output=True, text=True, check=True).stdout)["decks"][0]
area = round(wc * hc, 3)
print(json.dumps({
    "generator_command": "uv run --with klayout python3 layout/bitcell/generate.py",
    "verify_command": "./layout/verify.sh",
    "gds": {cell: sha(cell), tile: sha(tile)},
    "pitch_um": {"x": wc, "y": hc},
    "area_um2": area,
    "reference_area_um2": 3.50,
    "reference": "BITKIT_CELL_SUB 1.76 x 1.99 um (spec/bitcell-decision.md)",
    "area_ratio_vs_reference": round(area / 3.50, 2),
    "deck": {"name": "sg13g2", "content_hash": deck["content_hash"], "released": deck["released"],
             "release": deck.get("release"), "unmodeled_rules": deck["unmodeled_rules"]},
    "klt_version": subprocess.run(["klt", "--version"], capture_output=True, text=True).stdout.strip(),
}, indent=2))
EOF
echo "reports written to $OUT"

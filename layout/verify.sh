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

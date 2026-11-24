#!/usr/bin/env bash
# Regenerate the bitcell layout and re-run its cell-level checks (DRC, extract,
# LVS) -- a pre-check, not the macro signoff flow. Run from anywhere:
#
#     ./layout/verify.sh
#
# Needs klt (>= 0.8.0, sg13g2 deck) and uv on PATH for steps 1-9. Step 10 needs klt >= 0.9.0,
# which first carries `array-check`; it does not use the host klt at all but pins
# klayout-tools==0.9.1 through `uvx`, matching layout/reports/array-check-macro.json. Step 11
# (issue #228, the bitcell PEX digest) likewise bypasses the host klt: it pins `uvx` to the tool.klt_pin of the newest
# sim/bitcell/records/<UTC>/record.json it selects -- the pin that record was minted at.
# Step 12 (issue #229) validates the supply spec, checks layout/reports/erc-macro.json against its
# committed inputs and runs the erc negative controls (test_erc_controls.py; the controls
# run on the signoff-pinned klt through uvx, never the host klt). Nothing
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

hr "9. macro: the latest (supply-terminal routing, issue #231) record matches the committed layout; every tie, periphery supply D/S pad and riser reaches its rail; no rail below Metal4 in the wordline gap"
python3 - <<'PYEOF'
import hashlib, json, sys
rec_path = "layout/reports/macro-record-supply-terminals.json"
rec = json.load(open(rec_path))
for key in ("gds", "lef", "socket"):
    for path, want in rec[key].items():
        got = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if got != want:
            sys.exit(f"FAIL: {path} differs from {rec_path}")
if rec["leaf_signal_routing"]["undrawn"] or rec["hier_signal_routing"]["undrawn"]:
    sys.exit(f"FAIL: {rec_path} reports an undrawn signal net")
if rec["drc"]["status"] != "clean" or rec["drc"]["violation_count"] != 0:
    sys.exit(f"FAIL: {rec_path} reports a non-clean DRC result: {rec['drc']}")
c = rec["rails_connectivity"]
ds = c["supply_ds_pads"]
ok = (c["ties_on_own_rail"] == c["ties_expected"] and c["ties_floating"] == 0 and c["ties_on_other_rail"] == 0
      and c["vdd_vss_short_polygons"] == 0
      and all(v["on_rail"] == v["expected"] and v["on_other_rail"] == 0 for v in c["bitcell_risers"].values())
      and all(v["expected"] > 0 and v["on_own_rail"] == v["expected"] and v["on_other_rail"] == 0 and v["floating"] == 0
              for v in ds.values()))
if not ok:
    sys.exit(f"FAIL: {rec_path} reports a floating tie/D-S pad, a stray rail or a short")
if rec["rails_vs_wordline_gap"]["total"] != 0:
    sys.exit(f"FAIL: {rec_path} reports a rail shape below Metal4 in the wordline gap")
erc = rec["erc"]
if erc["isolated_periphery_supply_ds_islands"] != {"VDD": 0, "VSS": 0}:
    sys.exit(f"FAIL: {rec_path} reports isolated periphery supply D/S islands in ERC: {erc['isolated_periphery_supply_ds_islands']}")
if any(erc["supplies"][n]["matched_islands"] != 2 or erc["supplies"][n]["unlabelled_islands"] != 0 for n in ("VDD", "VSS")):
    sys.exit(f"FAIL: {rec_path} ERC island summary differs from expected 2 islands (trunk + pin square) per supply")
print(
    f"PASS: record matches the files; {c['ties_on_own_rail']}/{c['ties_expected']} ties, "
    f"{ds['VDD']['on_own_rail']}/{ds['VDD']['expected']} VDD D/S pads, "
    f"{ds['VSS']['on_own_rail']}/{ds['VSS']['expected']} VSS D/S pads and all bitcell risers on their rail; "
    "ERC 2 islands/supply (0 isolated D/S); wordline gap clear; no undrawn signal net"
)
PYEOF

hr "10. macro: array regularity (klt array-check; pinned klt 0.9.1 -- reproduces the committed report: layout/reports/array-check-macro.json records provenance klt_version 0.9.1)"
# The clip, the abutment/symmetry invocations, the assertions on them and the provenance checks
# live in the mint script's --check mode (issue #247): one owner for both modes, so the mint and
# this check cannot drift apart.
./layout/reports/generate-array-check.sh --check

hr "11. bitcell PEX: PDK-free extraction digest matches the latest klt pex record"
# The PDK-free half of the bitcell post-layout evidence (issue #228): the
# parasitic extraction `klt pex` performs is deterministic, so re-running it
# without a PDK install (CI has none) must reproduce the netlist digest the
# committed sim/bitcell/records/<UTC>/ pex record pins. The measured
# (PDK-bound, batch-fleet) legs are never re-run here; their envelope and the
# PDK-bound digest live in the record. klt is pinned to the selected record's
# own tool.klt_pin (not the CI KLT_VERSION) for the same reason as step 10:
# the committed digest was minted at that pin and is reproducible only there,
# and the host `klt` is a dev build.
PEXREC="$(ls -d "$ROOT"/sim/bitcell/records/*/pex-envelope.json 2>/dev/null | sort | tail -1 || true)"
if [ -z "$PEXREC" ]; then
  echo "FAIL: no klt pex record under sim/bitcell/records/ (run sim/bitcell/run_pex.sh)"; exit 1
fi
PEXDIR="$(dirname "$PEXREC")"
KLTPIN="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["tool"]["klt_pin"])' "$PEXDIR/record.json")"
KLTPEX=(uvx --from "klayout-tools==$KLTPIN" klt)
echo "re-extracting at klayout-tools==$KLTPIN (tool.klt_pin in $PEXDIR/record.json)"
rc=0
"${KLTPEX[@]}" pex "$CELL" --deck sg13g2 --extract-only --reference-netlist "$REF" \
  -o "$WORK/pex-free.spice" --envelope-out "$WORK/pex-free.json" \
  --outdir "$WORK/pex-free-out" --format json >/dev/null 2> "$WORK/pex-free.stderr" || rc=$?
# --extract-only measures nothing: exit 4 with a valid envelope is the result.
if [ "$rc" -ne 4 ]; then
  echo "FAIL: klt pex --extract-only exited $rc (want 4)"; tail -5 "$WORK/pex-free.stderr"; exit 1
fi
python3 -I - "$WORK/pex-free.spice" "$WORK/pex-free.json" "$PEXDIR" <<'PEXEOF'
import hashlib, json, sys
netlist, envelope, recdir = sys.argv[1:4]
got = hashlib.sha256(open(netlist, "rb").read()).hexdigest()
env = json.load(open(envelope))
rec = json.load(open(f"{recdir}/record.json"))
assert env["status"] == "not_checked", env["status"]
assert env["measurement"]["mode"] == "extract-only", env["measurement"]["mode"]
want = rec["extraction_digests"]["pdk_free_spice_sha256"]
if got != want:
    sys.exit(f"FAIL: PDK-free extraction digest {got} != {recdir}/record.json "
             f"pdk_free_spice_sha256 {want} -- the bitcell layout or the extraction "
             "deck changed, so mint a new pex record (records are append-only)")
# The generic-class model mismatch of the PDK-free deck (nfet/pfet vs the
# PDK-bound sg13_lv_*) is expected here and is quoted, not failed on.
mm = env["model_mismatch"]
kind = mm["kind"] if mm else None
print(f"PASS: PDK-free extraction digest matches {recdir}/record.json "
      f"(model_mismatch.kind={kind} on the PDK-free deck, as recorded)")
PEXEOF

hr "12. macro: supply spec current, as-built klt erc report reproduces, negative controls bite (issue #229)"
uv run --with klayout python3 $D/supply_spec.py
if git diff --quiet -- $D/macro.supply.json; then
  echo "PASS: macro.supply.json matches supply_spec.py output"
else
  echo "FAIL: macro.supply.json differs from supply_spec.py output"; exit 1
fi
# Always the signoff pin (the report's provenance), never whichever klt is on PATH.
KLT_PIN="$(sed -n 's/^  KLT_VERSION: "\(.*\)"$/\1/p' .github/workflows/signoff.yml)"
[ -n "$KLT_PIN" ] || { echo "cannot read KLT_VERSION from .github/workflows/signoff.yml"; exit 1; }
pinned_klt() { uvx --from "klayout-tools==$KLT_PIN" klt "$@"; }
pinned_klt erc --validate-spec $D/macro.supply.json
if pinned_klt erc --check layout/reports/erc-macro.json > /dev/null; then
  echo "PASS: layout/reports/erc-macro.json matches the committed macro.gds and spec (cheap hash mode)"
else
  echo "FAIL: erc-macro.json drifted from its inputs -- mint a new record (append-only), do not edit it"; exit 1
fi
(cd $D && uv run --with pytest --with klayout pytest -q test_erc_controls.py)

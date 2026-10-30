#!/usr/bin/env bash
# Mint the macro evidence record (issue #28; taps step of #88): regenerate the macro GDS, socket
# descriptor and LEF, then write layout/reports/macro-record-taps.json (macro-record.json is the #87
# result and is not rewritten). Run from
# anywhere:   ./layout/reports/generate-macro.sh
#
# Records are append-only evidence: a re-run after a layout or klt change is a
# new result -- commit it as such and say why in the commit message.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
D=layout/sram_256x32
# macro-record.json describes the unrouted macro of #28; the generator now draws the
# array-interface routing (#94), so a re-run would overwrite that record with other
# hashes. The current macro is recorded by generate-macro-routed.sh.
if [[ -s layout/reports/macro-record.json ]]; then
  echo "refusing to overwrite layout/reports/macro-record.json (append-only evidence);" >&2
  echo "use ./layout/reports/generate-macro-routed.sh for the current macro" >&2
  exit 1
fi
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

uv run --with klayout python3 $D/generate.py
klt socket-check --socket $D/macro.socket.json $D/macro.gds --format json > "$WORK/socket.json" || true
klt lef-abstract $D/macro.gds --socket $D/macro.socket.json --macro-name macro \
  --cell-library sg13g2_stdcell --pdk ihp-sg13g2 --obs-mode coarse -o $D/macro.lef --format json > "$WORK/lef.json"
klt cells --format json $D/macro.gds > "$WORK/cells.json"
klt extract --deck sg13g2 $D/macro.gds -o "$WORK/extracted.spice" --format json > "$WORK/extract.json"

python3 - "$WORK" <<'PYEOF' > layout/reports/macro-record-taps.json
import hashlib, json, subprocess, sys
w = sys.argv[1]
D = "layout/sram_256x32"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
cells = {c["name"]: c for c in json.load(open(f"{w}/cells.json"))["cells"]}
lef = json.load(open(f"{w}/lef.json"))
sock = json.load(open(f"{w}/socket.json"))
ext = json.load(open(f"{w}/extract.json"))
deck = json.loads(subprocess.run(["klt", "deck", "info", "--deck", "sg13g2", "--format", "json"],
                                 capture_output=True, text=True, check=True).stdout)["decks"][0]
sizes = json.load(open(f"{D}/macro.socket.json"))["outline"]
width, height = sizes["x1"] - sizes["x0"], sizes["y1"] - sizes["y0"]
area = round(width * height, 1)
bit = cells["bitcell"]
count = 128 * 64  # bl_pair holds 128 bitcell instances; macro holds 64 bl_pair via 32 bit_slice
print(json.dumps({
    "generator_command": "uv run --with klayout python3 layout/sram_256x32/generate.py",
    "record_command": "./layout/reports/generate-macro.sh",
    "gds": {f"{D}/macro.gds": sha(f"{D}/macro.gds")},
    "lef": {f"{D}/macro.lef": sha(f"{D}/macro.lef")},
    "socket": {f"{D}/macro.socket.json": sha(f"{D}/macro.socket.json")},
    "top_cell": "macro",
    "organization": "128 rows x 64 columns (mux 2), 32 bit_slice",
    "bitcell_instances_flattened": count,
    "bl_pair_bitcell_instances": cells["bl_pair"]["instances"],
    "bit_slice_instances": cells["bit_slice"]["instances"],
    "macro_size_um": {"x": round(width, 3), "y": round(height, 3)},
    "macro_area_um2": area,
    "array_area_um2": round(count * 2.87 * 3.605, 1),
    "reference_area_um2": 49488.5,
    "reference": "shipped sg13g2_sram 256x32 macro, 416.64 x 118.78 um (spec/bitcell-decision.md)",
    "area_ratio_vs_reference": round(area / 49488.5, 2),
    "socket_check": {k: sock.get(k) for k in ("status", "pins", "outline") if k in sock},
    "lef_pin_geometry_sources": sorted({p.get("geometry_source") for p in lef.get("pins", [])}),
    "lef_obs_mode": "coarse",
    "edge_and_corner_dummies": "none drawn (ties are in-cell)",
    "extract": {k: ext.get(k) for k in ("status", "device_count", "device_counts", "net_count", "pin_count")},
    "netlist_flattened_device_count": 51948,
    "netlist_flattened_device_counts": {"nfet": 34118, "pfet": 17830},
    "tap_step": "one body tie per periphery transistor (n+ Activ in the PMOS well, p+ Activ with pSD for NMOS), Metal1 pad labelled with the netlist bulk net; not yet wired to a rail",
    "not_drawn": ["supply rails and tie-to-rail connection", "periphery signal routing", "array-to-column-path and wordline routing", "pin routing"],
    "deck": {"name": "sg13g2", "content_hash": deck["content_hash"], "released": deck["released"],
             "release": deck.get("release")},
    "klt_version": subprocess.run(["klt", "--version"], capture_output=True, text=True).stdout.strip(),
}, indent=2))
PYEOF
echo "record written to layout/reports/macro-record-taps.json"

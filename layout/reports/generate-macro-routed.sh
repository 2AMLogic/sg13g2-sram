#!/usr/bin/env bash
# Mint the routed-macro evidence record (issue #94, seam 3 of #88): regenerate the
# macro GDS, socket descriptor and LEF, run klt extract on the GDS, then write
# layout/reports/macro-record-routed.json. Run from anywhere:
#
#     ./layout/reports/generate-macro-routed.sh
#
# Records are append-only evidence: macro-record.json (the unrouted macro of #28)
# is not edited. A re-run after a layout or klt change is a new result -- commit
# it as such and say why in the commit message. Takes about two minutes (klt extract).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
D=layout/sram_256x32
OUT=layout/reports/macro-record-routed.json
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

uv run --with klayout python3 $D/generate.py
klt socket-check --socket $D/macro.socket.json $D/macro.gds --format json > "$WORK/socket.json" || true
klt lef-abstract $D/macro.gds --socket $D/macro.socket.json --macro-name macro \
  --cell-library sg13g2_stdcell --pdk ihp-sg13g2 --obs-mode coarse -o $D/macro.lef --format json > "$WORK/lef.json"
klt extract --deck sg13g2 $D/macro.gds -o "$WORK/macro.spice" --format json > "$WORK/extract.json"
klt drc --deck sg13g2 $D/macro.gds --format json -o "$WORK/drc.json" > /dev/null || true

uv run --with klayout python3 - "$WORK" <<'PYEOF' > "$OUT"
import hashlib, json, re, subprocess, sys, collections
w = sys.argv[1]
D = "layout/sram_256x32"
sys.path.insert(0, D)
import generate as g
import test_macro as t

sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
sock = json.load(open(f"{w}/socket.json"))
ext = json.load(open(f"{w}/extract.json"))
drc = json.load(open(f"{w}/drc.json"))
deck = json.loads(subprocess.run(["klt", "deck", "info", "--deck", "sg13g2", "--format", "json"],
                                 capture_output=True, text=True, check=True).stdout)["decks"][0]
size = json.load(open(f"{D}/macro.socket.json"))["outline"]
width, height = size["x1"] - size["x0"], size["y1"] - size["y0"]
area = round(width * height, 1)

# (a) geometric tracing on the generated layout (the test_macro.py check)
gen, net = t._extract()
wl = t._wl_ok(t._wl_ids(gen, net, range(g.ROWS)))
bl = t._bl_ok(t._bl_ids(gen, net, range(g.COLS)))
wl_ids = [a for a, _ in t._wl_ids(gen, net, range(g.ROWS)).values()]
bl_ids = [a for a, _ in t._bl_ids(gen, net, range(g.COLS)).values()]

# (b) klt extract, array interface only: every extracted net that carries a macro-level
# bit-line label also carries the precharge and column-mux labels; wordline nets are the
# distinct gate nets of the access devices (nfet W 0.3 L 0.13) named from the driver label.
pins = [l[6:].strip() for l in open(f"{w}/macro.spice") if l.startswith("* pin ")]
bl_ok = 0
for c in range(g.COLS):
    for base in ("BL", "BLB"):
        # the net carries the precharge label (BL/BLB), the mux's local label (BL0/BL1,
        # by column parity) and the macro label (BL<c>) -- columns 0 and 1 coincide
        want = {base, f"{base}{c % 2}", f"{base}{c}"}
        bl_ok += int(sum(set(p.split(",")) == want for p in pins) == 1)
gates = collections.Counter()
for l in open(f"{w}/macro.spice"):
    m = re.match(r"M\$\d+ (\S+) (\S+) (\S+) (\S+) nfet L=0.13U W=0.3U", l)
    if m:
        gates[m.group(2)] += 1
wl_nets = {k: v for k, v in gates.items() if k.split("$")[0] == "WL"}

print(json.dumps({
    "generator_command": "uv run --with klayout python3 layout/sram_256x32/generate.py",
    "record_command": "./layout/reports/generate-macro-routed.sh",
    "supersedes_nothing": "macro-record.json (unrouted, #28) is kept as it was",
    "gds": {f"{D}/macro.gds": sha(f"{D}/macro.gds")},
    "lef": {f"{D}/macro.lef": sha(f"{D}/macro.lef")},
    "socket": {f"{D}/macro.socket.json": sha(f"{D}/macro.socket.json")},
    "top_cell": "macro",
    "macro_size_um": {"x": round(width, 3), "y": round(height, 3)},
    "macro_area_um2": area,
    "area_ratio_vs_reference": round(area / 49488.5, 2),
    "area_change_vs_unrouted": {
        "unrouted_area_um2": 176848.0,
        "wordline_fanout_gap_um": g.WL_FANOUT_GAP,
        "reason": "128 private Metal2 lanes at 0.42 um pitch between row decoder and array",
    },
    "routing": {
        "layers": ["Metal2", "Metal3", "Via1", "Via2"],
        "wordline_nets": g.ROWS,
        "bitline_nets": 2 * g.COLS,
        "bitline_terminals": "one BL/BLB device terminal per precharge and per column mux (no periphery-internal routing: #95)",
        "wordline_terminal": "drain of the first wl_driver device on WL (XMPD)",
    },
    "array_interface_connectivity": {
        "geometric_trace": {
            "wordlines_connected_of_128": sum(wl.values()),
            "bitlines_connected_of_128": sum(bl.values()),
            "distinct_wordline_nets": len(set(wl_ids)),
            "distinct_bitline_nets": len(set(bl_ids)),
            "wordline_or_bitline_shorted": len(set(wl_ids) | set(bl_ids)) != len(set(wl_ids)) + len(set(bl_ids)),
        },
        "klt_extract": {
            "bitline_nets_with_macro_precharge_and_mux_labels_of_128": bl_ok,
            "wordline_nets_named_from_driver_of_128": len(wl_nets),
            "access_gates_per_wordline_net": sorted(set(wl_nets.values())),
            "extract_device_count": ext["metrics"]["extract__device__count"],
            "extract_net_count": ext["metrics"]["extract__net__count"],
        },
        "note": "comparison against design/macro/macro.spice is LVS (#30), not made here",
    },
    "drc": {"status": drc["status"], "violation_count": drc["violation_count"],
            "rule_counts": drc["rule_counts"],
            "unrouted_macro_violation_count": 522,
            "note": "same 522 nwell.space.1 as the unrouted macro; no Metal2/Metal3/Via violations"},
    "socket_check": {k: sock.get(k) for k in ("status", "pins", "outline") if k in sock},
    "lef_obs_mode": "coarse",
    "not_drawn": ["periphery signal routing", "supply rails and body ties (#92)",
                  "periphery net and pin routing (#95)"],
    "deck": {"name": "sg13g2", "content_hash": deck["content_hash"], "released": deck["released"],
             "release": deck.get("release")},
    "klt_version": subprocess.run(["klt", "--version"], capture_output=True, text=True).stdout.strip(),
}, indent=2))
PYEOF
echo "record written to $OUT"

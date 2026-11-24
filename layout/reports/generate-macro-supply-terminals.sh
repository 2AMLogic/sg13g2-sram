#!/usr/bin/env bash
# Mint the periphery supply-terminal routing evidence record (issue #231): regenerate the
# macro GDS, socket descriptor and LEF, re-mint layout/reports/erc-macro.json against the
# committed supply spec and layout/reports/drc-macro.json at the signoff pin
# (generate-drc-macro.sh, #251), and write layout/reports/macro-record-supply-terminals.json.
# Earlier records (macro-record.json through macro-record-blbm.json) pin earlier GDS
# hashes and are append-only evidence -- they are not rewritten. `layout/verify.sh` step 9
# reads this record. Run from anywhere:
#
#     ./layout/reports/generate-macro-supply-terminals.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
D=layout/sram_256x32
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

(cd "$D" && uv run --with klayout python3 -I - "$WORK/analysis.json" <<'PYEOF'
import json, sys
sys.path.insert(0, ".")
import generate as g, rails_check as rc

layout, gen, top = g.build()
layout.write(g.GDS_PATH, g.save_options())
with open(g.SOCKET_PATH, "w") as f:
    json.dump(g.socket(gen, top), f, indent=2)
    f.write("\n")
with open(sys.argv[1], "w") as f:
    json.dump(
        {
            "rails": rc.analyse(layout, top, gen),
            "gap": rc.wordline_gap_clearance(layout, top, gen),
            "leaf": gen.leaf_report,
            "hier": gen.hier_report,
            "stubs": [t["stub"] for t in gen.tie_wiring],
            "ds_stubs": [d["stub"] for d in gen.ds_wiring],
        },
        f,
    )
PYEOF
)

klt socket-check --socket $D/macro.socket.json $D/macro.gds --format json > "$WORK/socket.json" || true
klt lef-abstract $D/macro.gds --socket $D/macro.socket.json --macro-name macro \
  --cell-library sg13g2_stdcell --pdk ihp-sg13g2 --obs-mode coarse -o $D/macro.lef --format json > "$WORK/lef.json"
klt extract --deck sg13g2 $D/macro.gds -o "$WORK/extracted.spice" --format json > "$WORK/extract.json"
# drc-macro.json is minted by its own generator at the signoff pin (#251): the
# committed record must cite the released deck the pin ships, never whichever
# (possibly dev-build) klt is on PATH -- the mint asserts clean, released and
# input-bound before replacing the committed report.
./layout/reports/generate-drc-macro.sh
./layout/reports/generate-erc-macro.sh

python3 - "$WORK" <<'PYEOF' > "$WORK/record.json"
import collections, hashlib, json, subprocess, sys
w = sys.argv[1]
D = "layout/sram_256x32"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
lef = json.load(open(f"{w}/lef.json"))
sock = json.load(open(f"{w}/socket.json"))
ext = json.load(open(f"{w}/extract.json"))
drc = json.load(open("layout/reports/drc-macro.json"))
erc = json.load(open("layout/reports/erc-macro.json"))
an = json.load(open(f"{w}/analysis.json"))
deck = json.loads(subprocess.run(["klt", "deck", "info", "--deck", "sg13g2", "--format", "json"],
                                 capture_output=True, text=True, check=True).stdout)["decks"][0]
sizes = json.load(open(f"{D}/macro.socket.json"))["outline"]
width, height = sizes["x1"] - sizes["x0"], sizes["y1"] - sizes["y0"]
leaf = an["leaf"]
rails = an["rails"]
ds = rails["supply_ds_pads"]

def classify_island(isl: dict) -> str:
    if isl["layer"] == "metal4":
        return "internal_rail_and_trunk"
    if isl["layer"] == "metal2" and isl["shape_count"] == 1:
        return "boundary_pin_square (#108)"
    if isl["layer"] == "metal1":
        return "isolated_periphery_ds_pad"
    return f"other ({isl['layer']})"

erc_by_net = {}
isolated_ds_erc = {}
findings_by_net = {f["net"]: f for f in erc["erc_findings"] if f.get("net") in ("VDD", "VSS")}
for net_entry in erc["nets"]:
    net = net_entry["name"]
    f = findings_by_net.get(net, {"islands": []})
    rem = []
    iso_m1 = 0
    for isl in f.get("islands", []):
        kind = classify_island(isl)
        if isl["layer"] == "metal1":
            iso_m1 += 1
        rem.append({
            "identity": kind,
            "layer": isl["layer"],
            "shape_count": isl["shape_count"],
            "bbox_dbu": isl["bbox"],
        })
    isolated_ds_erc[net] = iso_m1
    erc_by_net[net] = {
        "matched_islands": net_entry["matched_islands"],
        "expected_islands": net_entry["expected_islands"],
        "unlabelled_islands": net_entry["unlabelled_islands"],
        "isolated_periphery_ds_islands": iso_m1,
        "remaining_islands": rem,
    }

print(json.dumps({
    "generator_command": "uv run --with klayout python3 layout/sram_256x32/generate.py",
    "record_command": "./layout/reports/generate-macro-supply-terminals.sh",
    "issue": 231,
    "gds": {f"{D}/macro.gds": sha(f"{D}/macro.gds")},
    "lef": {f"{D}/macro.lef": sha(f"{D}/macro.lef")},
    "socket": {f"{D}/macro.socket.json": sha(f"{D}/macro.socket.json")},
    "top_cell": "macro",
    "macro_size_um": {"x": round(width, 3), "y": round(height, 3)},
    "macro_area_um2": round(width * height, 1),
    "socket_check": {k: sock.get(k) for k in ("status", "pins", "outline") if k in sock},
    "lef_pin_geometry_sources": sorted({p.get("geometry_source") for p in lef.get("pins", [])}),
    "extract": {k: ext.get(k) for k in ("status", "device_count", "device_counts", "net_count", "pin_count")},
    "drc": {"status": drc.get("status"), "violation_count": drc.get("violation_count"),
            "rule_counts": drc.get("rule_counts"), "report": "layout/reports/drc-macro.json"},
    "supply_terminal_coverage": {
        "probe_source": "rails_check.supply_ds_terminals (independent netlist flat_nets + GDS transistor geometry)",
        "VDD": {
            "expected": ds["VDD"]["expected"],
            "connected_to_own_trunk": ds["VDD"]["on_own_rail"],
            "connected_to_opposite_trunk": ds["VDD"]["on_other_rail"],
            "floating": ds["VDD"]["floating"],
        },
        "VSS": {
            "expected": ds["VSS"]["expected"],
            "connected_to_own_trunk": ds["VSS"]["on_own_rail"],
            "connected_to_opposite_trunk": ds["VSS"]["on_other_rail"],
            "floating": ds["VSS"]["floating"],
        },
        "before_issue_231": {
            "baseline_gds_sha256": "e0a06f5f06a6b84ee053e4f8f3a5996d2a54681a78494083cc06192677cfbff6",
            "ties_on_own_rail": 2796,
            "ties_floating": 0,
            "VDD": {"expected": 1038, "connected_to_own_trunk": 0, "connected_to_opposite_trunk": 0, "floating": 1038},
            "VSS": {"expected": 620, "connected_to_own_trunk": 0, "connected_to_opposite_trunk": 0, "floating": 620},
            "vdd_vss_short_polygons": 0,
        },
    },
    "erc": {
        "report": "layout/reports/erc-macro.json",
        "spec": f"{D}/macro.supply.json",
        "spec_sha256": sha(f"{D}/macro.supply.json"),
        "klt_version": erc["provenance"]["klt_version"],
        "erc_status": erc["erc_status"],
        "isolated_periphery_supply_ds_islands": isolated_ds_erc,
        "supplies": erc_by_net,
        "before_issue_231": {
            "baseline_gds_sha256": "e0a06f5f06a6b84ee053e4f8f3a5996d2a54681a78494083cc06192677cfbff6",
            "VDD": {"matched_islands": 1040, "isolated_periphery_ds_islands": 1038},
            "VSS": {"matched_islands": 622, "isolated_periphery_ds_islands": 620},
        },
    },
    "leaf_signal_routing": {
        "router": "MazeRouter (generate.py): Metal2/Metal3 maze on a 0.05 um lattice, Via1 landings on the Metal1 terminals, "
                  "nets of two or more D/G/S terminals; supply, bit-line and wordline nets are not routed here",
        "blbm_join": "issue #159: route_bitlines keeps every bit-line jog clear of the column_mux BLBM terminal bands "
                     "(blbm_reserve: BLBM_CROSSING_CLEAR = M3.a + M3.b of Metal3 kept under each band, "
                     "BLBM_JOGLANE_CLEAR = M2.a/2 + M2.b right of the jog's own M2 column), and route_leaf joins the net "
                     "in the freed Metal3 under each band's jog lane; with it every leaf-cell net of every cell is drawn",
        "cells": {name: {"routed_nets": rep["routed"], "single_terminal_nets": rep["single_terminal"],
                         "excluded_nets": sorted(rep["excluded"]), "undrawn_nets": rep["failed"]}
                  for name, rep in sorted(leaf.items())},
        "routed_net_count": sum(len(r["routed"]) for r in leaf.values()),
        "undrawn": [f"{n}/{x}" for n, r in sorted(leaf.items()) for x in r["failed"]],
        "connectivity_check": "test_macro.py::test_leaf_cell_nets_are_one_net_each_and_never_short (per-cell extraction)"
                              " and test_macro.py::test_column_mux_blbm_is_one_net_and_has_teeth (BLBM)",
    },
    "hier_signal_routing": {
        "router": "MazeRouter (generate.py) over the child cells of addr_latch, data_latch, out_latch, control, predec3, predec4, wl_drivers and "
                  "row_decoder: one terminal per instance port; the children's own Metal2/Metal3, the body-tie pads and the wordline stubs and "
                  "tracks are obstacles except the nets being joined; supply and wordline nets are not routed",
        "cells": {name: {"routed_nets": rep["routed"], "single_terminal_nets": rep["single_terminal"],
                         "excluded_nets": sorted(rep["excluded"]), "undrawn_nets": rep["failed"]}
                  for name, rep in sorted(an["hier"].items())},
        "routed_net_count": sum(len(r["routed"]) for r in an["hier"].values()),
        "undrawn": [f"{n}/{x}" for n, r in sorted(an["hier"].items()) for x in r["failed"]],
        "connectivity_check": "test_macro.py::test_hier_cell_nets_are_one_net_each_and_never_short (per-cell extraction)",
    },
    "tie_stubs": dict(collections.Counter(an["stubs"])),
    "ds_stubs": dict(collections.Counter(an["ds_stubs"])),
    "rails_vs_wordline_gap": an["gap"],
    "rails_connectivity": rails,
    "not_drawn": ["VDD/VSS pin connection to the rails", "signal nets between the blocks",
                  "inter-block signal fan-out", "signal pin routing"],
    "deck": {"name": "sg13g2", "content_hash": deck["content_hash"], "released": deck["released"],
             "release": deck.get("release")},
    "klt_version": subprocess.run(["klt", "--version"], capture_output=True, text=True).stdout.strip(),
}, indent=2))
PYEOF
mv "$WORK/record.json" layout/reports/macro-record-supply-terminals.json
echo "record written to layout/reports/macro-record-supply-terminals.json"

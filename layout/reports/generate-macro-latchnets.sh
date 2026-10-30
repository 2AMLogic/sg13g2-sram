#!/usr/bin/env bash
# Mint the latch/control signal-routing evidence record (issue #106): regenerate the macro GDS, socket
# descriptor and LEF, then write layout/reports/macro-record-latchnets.json. The earlier records
# (macro-record.json, -taps, -routed, -rails, -leafnets) are results of earlier layouts and are not rewritten;
# this record re-states the rails and wordline-gap checks on the new layout so `verify.sh` step 9
# has a record that matches the committed files. Run from anywhere:
#
#     ./layout/reports/generate-macro-latchnets.sh
#
# Records are append-only evidence: a re-run after a layout or klt change is a new result -- commit
# it as such and say why in the commit message.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
D=layout/sram_256x32
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

uv run --with klayout python3 $D/generate.py
klt socket-check --socket $D/macro.socket.json $D/macro.gds --format json > "$WORK/socket.json" || true
klt lef-abstract $D/macro.gds --socket $D/macro.socket.json --macro-name macro \
  --cell-library sg13g2_stdcell --pdk ihp-sg13g2 --obs-mode coarse -o $D/macro.lef --format json > "$WORK/lef.json"
klt extract --deck sg13g2 $D/macro.gds -o "$WORK/extracted.spice" --format json > "$WORK/extract.json"
klt drc --deck sg13g2 --top macro $D/macro.gds --format json > "$WORK/drc.json" || true

(cd $D && uv run --with klayout python3 -I -c 'import json,sys; sys.path.insert(0, "."); import generate as g, rails_check as rc; l,gen,top=g.build(); print(json.dumps({"rails": rc.analyse(l,top,gen), "gap": rc.wordline_gap_clearance(l,top,gen), "leaf": gen.leaf_report, "hier": gen.hier_report, "stubs": [t["stub"] for t in gen.tie_wiring]}))' > "$WORK/analysis.json")
python3 - "$WORK" <<'PYEOF' > layout/reports/macro-record-latchnets.json
import collections, hashlib, json, subprocess, sys
w = sys.argv[1]
D = "layout/sram_256x32"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
lef = json.load(open(f"{w}/lef.json"))
sock = json.load(open(f"{w}/socket.json"))
ext = json.load(open(f"{w}/extract.json"))
drc = json.load(open(f"{w}/drc.json"))
an = json.load(open(f"{w}/analysis.json"))
deck = json.loads(subprocess.run(["klt", "deck", "info", "--deck", "sg13g2", "--format", "json"],
                                 capture_output=True, text=True, check=True).stdout)["decks"][0]
sizes = json.load(open(f"{D}/macro.socket.json"))["outline"]
width, height = sizes["x1"] - sizes["x0"], sizes["y1"] - sizes["y0"]
leaf = an["leaf"]
print(json.dumps({
    "generator_command": "uv run --with klayout python3 layout/sram_256x32/generate.py",
    "record_command": "./layout/reports/generate-macro-latchnets.sh",
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
            "rule_counts": drc.get("rule_counts")},
    "leaf_signal_routing": {
        "router": "MazeRouter (generate.py): Metal2/Metal3 maze on a 0.05 um lattice, Via1 landings on the Metal1 terminals, "
                  "nets of two or more D/G/S terminals; supply, bit-line and wordline nets are not routed here",
        "cells": {name: {"routed_nets": rep["routed"], "single_terminal_nets": rep["single_terminal"],
                         "excluded_nets": sorted(rep["excluded"]), "undrawn_nets": rep["failed"]}
                  for name, rep in sorted(leaf.items())},
        "routed_net_count": sum(len(r["routed"]) for r in leaf.values()),
        "undrawn": [f"{n}/{x}" for n, r in sorted(leaf.items()) for x in r["failed"]],
        "connectivity_check": "test_macro.py::test_leaf_cell_nets_are_one_net_each_and_never_short (per-cell extraction)",
    },
    "latch_control_signal_routing": {
        "router": "MazeRouter (generate.py) over the leaf cells of addr_latch, data_latch, out_latch and control: one terminal per "
                  "instance port; the leaf cells' own Metal2/Metal3 are obstacles except the nets being joined; supply nets are not routed",
        "cells": {name: {"routed_nets": rep["routed"], "single_terminal_nets": rep["single_terminal"],
                         "excluded_nets": sorted(rep["excluded"]), "undrawn_nets": rep["failed"]}
                  for name, rep in sorted(an["hier"].items())},
        "routed_net_count": sum(len(r["routed"]) for r in an["hier"].values()),
        "undrawn": [f"{n}/{x}" for n, r in sorted(an["hier"].items()) for x in r["failed"]],
        "connectivity_check": "test_macro.py::test_hier_cell_nets_are_one_net_each_and_never_short (per-cell extraction)",
    },
    "tie_stubs": dict(collections.Counter(an["stubs"])),
    "rails_vs_wordline_gap": an["gap"],
    "rails_connectivity": an["rails"],
    "not_drawn": ["VDD/VSS pin connection to the rails", "row_decoder signal routing", "signal nets between the latch/control cells and the rest of the macro",
                  "inter-block signal fan-out", "signal pin routing", "column_mux BLBM (listed in undrawn)"],
    "deck": {"name": "sg13g2", "content_hash": deck["content_hash"], "released": deck["released"],
             "release": deck.get("release")},
    "klt_version": subprocess.run(["klt", "--version"], capture_output=True, text=True).stdout.strip(),
}, indent=2))
PYEOF
echo "record written to layout/reports/macro-record-latchnets.json"

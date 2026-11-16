#!/usr/bin/env bash
# Mint the inter-block fan-out evidence record (issue #107): regenerate the macro GDS, socket
# descriptor and LEF, then write layout/reports/macro-record-fanout.json. The earlier records
# (macro-record.json, -taps, -routed, -rails, -leafnets, -latchnets, -decoder) are results of earlier layouts
# and are not rewritten; this record re-states the rails and wordline-gap checks on the new layout so
# `verify.sh` step 9 has a record that matches the committed files. Run from anywhere:
#
#     ./layout/reports/generate-macro-fanout.sh
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
# the macro DRC record is what verify.sh step 8 re-checks, so it is minted here from the same run
klt drc --deck sg13g2 --top macro $D/macro.gds --format json > layout/reports/drc-macro.json || true
cp layout/reports/drc-macro.json "$WORK/drc.json"

(cd $D && uv run --with klayout python3 -I -c 'import json,sys; sys.path.insert(0, "."); import generate as g, rails_check as rc; l,gen,top=g.build(); print(json.dumps({"rails": rc.analyse(l,top,gen), "gap": rc.wordline_gap_clearance(l,top,gen), "leaf": gen.leaf_report, "hier": gen.hier_report, "stubs": [t["stub"] for t in gen.tie_wiring], "fanout": gen.fanout_report, "escape": {k: {"pins": v, "report": gen.escape_report.get(k, {})} for k, v in gen.escape_pins.items()}, "probes": {n: len(p) for n, p in gen.fanout_probes().items()}}))' > "$WORK/analysis.json")
python3 - "$WORK" <<'PYEOF' > layout/reports/macro-record-fanout.json
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
    "record_command": "./layout/reports/generate-macro-fanout.sh",
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
    "inter_block_fanout": {
        "router": "route_fanout (generate.py): a reserved-track channel router over the escape pins -- one horizontal Metal3 trunk "
                  "per net in the channel below the slices, one vertical Metal2 lane per net and side (west of the address latch, "
                  "and in the wordline fan-out gap below the array), one Metal3 track per net in the decoder approach band. A lane "
                  "and a trunk cross on different layers; the only vias are where a net turns",
        "escape_router": "MazeRouter: route_slice_escape brings the nine bit_slice ports to reserved Metal2 pins on the slice's "
                         "bottom edge (drawn once for all 32 slices); route_hier brings the BLOCK_ESCAPES ports of addr_latch, "
                         "control, row_decoder, data_latch and out_latch to a pin the maze picks on one block edge (connect_edge), "
                         "on the layer the macro level carries on in, so the two wires merge with no via on the boundary",
        "nets_wired": an["fanout"]["nets"],
        "net_count": len(an["fanout"]["nets"]),
        "terminals_probed_per_net": an["probes"],
        "trunk_tracks": len(an["fanout"]["trunks"]),
        "west_lanes": len(an["fanout"]["west_lanes"]),
        "gap_lanes": len(an["fanout"]["gap_lanes"]),
        "decoder_approach_tracks": len(an["fanout"]["decoder_approach"]),
        "channel_height_um": an["fanout"]["channel_h"],
        "slice_pin_offsets_um": an["fanout"]["slice_pins"],
        "slice_pin_y_um": an["fanout"]["slice_pin_y"],
        "escape_pins": {k: len(v["pins"]) for k, v in sorted(an["escape"].items())},
        "escape_undrawn": {k: v["report"].get("failed", []) for k, v in sorted(an["escape"].items())
                           if v["report"].get("failed")},
        "dangling_by_design": an["fanout"]["dangling_by_design"],
        "slice_internal_not_drawn": an["fanout"]["slice_internal_not_drawn"],
        "connectivity_check": "test_macro.py::test_fanout_nets_are_one_net_each_and_never_short (flat extraction at every "
                              "Metal1 device terminal of every net, in every block and all 32 slices), with "
                              "test_fanout_trace_has_teeth_across_the_whole_array and "
                              "test_per_slice_data_nets_trace_to_both_ends_of_the_array for the teeth",
    },
    "tie_stubs": dict(collections.Counter(an["stubs"])),
    "rails_vs_wordline_gap": an["gap"],
    "rails_connectivity": an["rails"],
    "not_drawn": ["VDD/VSS pin connection to the rails", "signal pin routing (issue #108)",
                  "bit_slice BLM and BLBM between the column mux, sense amplifier and write driver "
                  "(inside the slice, so outside issue #107; listed in slice_internal_not_drawn)",
                  "column_mux BLBM (listed in undrawn)",
                  "DOUTB[i] (dangling by design: no terminal outside slice i)"],
    "deck": {"name": "sg13g2", "content_hash": deck["content_hash"], "released": deck["released"],
             "release": deck.get("release")},
    "klt_version": subprocess.run(["klt", "--version"], capture_output=True, text=True).stdout.strip(),
}, indent=2))
PYEOF
echo "records written to layout/reports/macro-record-fanout.json and layout/reports/drc-macro.json"

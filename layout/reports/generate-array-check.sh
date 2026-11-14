#!/usr/bin/env bash
# Mint the array-regularity evidence record (issue #160): run `klt array-check` on the committed
# macro and on the 2x2 bitcell tile, then write layout/reports/array-check-macro.json. Nothing is
# regenerated and no existing report is rewritten -- this reads the committed GDS only. Run from
# anywhere:
#
#     ./layout/reports/generate-array-check.sh
#
# Records are append-only evidence: a re-run after a layout or klt change is a new result -- commit
# it as such and say why in the commit message. In particular the record pins the sha256 of
# layout/sram_256x32/macro.gds; if the generator ever re-emits that file, this record is NOT edited,
# a changed array mints a new result.
#
# Two deliberate klt pins live in this repo, for different purposes -- do not "unify" them:
#   * klayout-tools==0.8.0 (KLT_VERSION in .github/workflows/*.yml, attest/*.envelope.json) is the
#     signoff pin. Bumping it would force every attest envelope to be regenerated.
#   * klayout-tools==0.9.1 (this script) is the report pin. `array-check` does not exist in 0.8.0
#     (`invalid choice: 'array-check'`); it arrived in 0.9.0. 0.9.1 is the latest release, so the
#     record is reproducible from PyPI rather than from a host dev build. See #155.
# The pin is invoked through `uvx --from`, never installed onto the host.
#
# `klt array-check --format json` emits no `provenance` block (its sibling `klt drc` does -- see
# layout/reports/drc-macro.json). So this script adds provenance itself, in drc-macro.json's shape,
# sourcing klt_version/klayout_version from `klt env-provenance emit`. The host-specific fields that
# helper also emits (host_id, os, python_version) are deliberately dropped: the record must be
# byte-for-byte reproducible on any host, not just the one that minted it. That gap is filed
# upstream (klayout-tools#5698).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

KLT_PIN="klayout-tools==0.9.1"
K=(uvx --from "$KLT_PIN" klt)

MACRO=layout/sram_256x32/macro.gds
TILE=layout/bitcell/sg13g2_sram_bitcell_tile2x2.gds
OUT=layout/reports/array-check-macro.json

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# `array-check`'s abutment mode is one-dimensional: pointed at the whole macro with --cell bitcell
# it finds all 8192 placements (every column at once) while measuring array length along a single
# column, so `length == count x pitch` is unsatisfiable at any pitch/count. Clipping one column out
# is the only way to scope the abutment check to one axis today (klayout-tools#5698).
"${K[@]}" clip "$MACRO" --cell bl_pair -o "$WORK/bl_pair.gds" > /dev/null

# array-check exits 3 on `violated` -- a successful run with findings, not an error. Capture it.
run() { # run <out.json> <args...>
  local out="$1"; shift
  local rc=0
  "${K[@]}" array-check "$@" --format json > "$out" || rc=$?
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 3 ]; then
    echo "FAIL: klt array-check exited $rc" >&2; exit "$rc"
  fi
}

run "$WORK/slice.json"    "$MACRO"             --cell bit_slice    --pitch 5.74  --count 32  --direction x --tolerance 0.48
run "$WORK/column.json"   "$WORK/bl_pair.gds"  --cell bitcell      --pitch 3.605 --count 128 --direction y --tolerance 0.27
run "$WORK/symmetry.json" "$WORK/bl_pair.gds"  --cell bl_pair      --translate '0,7.21' --layers '[[1,0],[5,0],[8,0],[10,0]]'
run "$WORK/tile.json"     "$TILE"              --cell bitcell_leaf --pitch 2.87  --count 2   --direction x

"${K[@]}" env-provenance emit --path macro="$MACRO" --path tile="$TILE" --format json > "$WORK/env.json"

python3 -I - "$WORK" "$MACRO" "$TILE" "$KLT_PIN" <<'PYEOF' > "$OUT"
import hashlib, json, sys

work, macro, tile, pin = sys.argv[1:5]
sha = lambda p: "sha256:" + hashlib.sha256(open(p, "rb").read()).hexdigest()
load = lambda n: json.load(open(f"{work}/{n}.json"))
env = load("env")

# The clipped column is a derived intermediate in a mktemp dir; klt records its absolute path in
# `file`. Replace that with a stable logical name so the record is byte-for-byte reproducible, and
# pin the intermediate by content hash instead.
CLIP_LABEL = "(derived) bl_pair column clipped from layout/sram_256x32/macro.gds"
def result(name, source):
    r = load(name)
    if source == CLIP_LABEL:
        r["file"] = CLIP_LABEL
    return r

clip_cmd = "klt clip layout/sram_256x32/macro.gds --cell bl_pair -o <work>/bl_pair.gds"
invocations = [
    {
        "name": "macro-slice-abutment",
        "intent": "the 32 bit_slice columns abut along x at the slice pitch",
        "command": "klt array-check layout/sram_256x32/macro.gds --cell bit_slice"
                   " --pitch 5.74 --count 32 --direction x --tolerance 0.48 --format json",
        "input": macro,
        "input_content_hash": sha(macro),
        "tolerance_rationale": "0.48 um is the measured shared-edge overlap of the column seam -- the"
                               " mirror abutment of the two bl_pair halves shares that edge by design"
                               " (layout/README.md, 'Supply rails'). At --tolerance 0 the same run"
                               " reports that 0.48 um as an overlap. It is not slack.",
        "expectation": "clean",
        "result": result("slice", macro),
    },
    {
        "name": "macro-column-abutment",
        "intent": "the 128 bitcells of one column abut along y at the mirrored-pair half pitch",
        "command": f"{clip_cmd} && klt array-check <work>/bl_pair.gds --cell bitcell"
                   " --pitch 3.605 --count 128 --direction y --tolerance 0.27 --format json",
        "input": CLIP_LABEL,
        "input_content_hash": sha(f"{work}/bl_pair.gds"),
        "input_derived_from": {macro: sha(macro)},
        "tolerance_rationale": "0.27 um is the measured shared-edge overlap of the row seam, where the"
                               " mirror abutment merges the bitcell VDD/VSS risers (layout/README.md,"
                               " 'Supply rails'). At --tolerance 0 the run reports 0.27 um / 0.15 um"
                               " seam overlaps and a 0.15 um length error; a sweep gives 64 violations"
                               " at 0.15 and clean at 0.27. It is not slack.",
        "expectation": "clean",
        "result": result("column", CLIP_LABEL),
    },
    {
        "name": "column-translation-symmetry",
        "intent": "one column is invariant under a one-mirrored-pair (+7.21 um) y translation",
        "command": f"{clip_cmd} && klt array-check <work>/bl_pair.gds --cell bl_pair"
                   " --translate '0,7.21' --layers '[[1,0],[5,0],[8,0],[10,0]]' --format json",
        "input": CLIP_LABEL,
        "input_content_hash": sha(f"{work}/bl_pair.gds"),
        "input_derived_from": {macro: sha(macro)},
        "expectation": "characterized: 8 residuals in exactly two y bands, both explained below."
                       " NOT a pass, and NOT to be tolerance-tuned away -- raising --tolerance until"
                       " this reports clean would mask a future break of interior symmetry. The"
                       " residual count and the two bands are the regression guard.",
        "characterization": {
            "residual_count": 8,
            "y_bands_um": [[7.065, 7.355], [461.440, 461.585]],
            "by_layer": {"1/0": 2, "8/0": 4, "10/0": 2, "5/0": 0},
            "why_not_a_defect": [
                "y 7.065..7.355 is the finite-array end: under a +7.21 um shift no partner geometry"
                " exists beyond the last mirrored pair, so the edge cannot be symmetric. An infinite"
                " array would have no residual here.",
                "y 461.440..461.585 is seam 0, which layout/README.md already records as special: it"
                " sits on the bit-line Via1/Via2 stacks below the array, so it is a pad per column"
                " plus a Metal4 strap instead of the full-width Metal2 strap every other seam gets.",
                "The array interior is residual-free: no residual lies between the two bands.",
            ],
        },
        "result": result("symmetry", CLIP_LABEL),
    },
    {
        "name": "tile2x2-abutment-limitation",
        "intent": "minimal reproducer of the one-dimensional abutment model, on the committed 2x2"
                  " mirror tile (4 bitcell_leaf placements, 2 x 2)",
        "command": f"klt array-check {tile} --cell bitcell_leaf"
                   " --pitch 2.87 --count 2 --direction x --format json",
        "input": tile,
        "input_content_hash": sha(tile),
        "expectation": "violated: a tool limitation, not a layout defect. The check counts every"
                       " placement in the 2-D tile (4) against the per-row count (2), measures array"
                       " length across both rows (6.22 um != 2 x 2.87 um), and projects the two"
                       " y-stacked placements onto x as spurious full-cell 3.35 um overlaps. The same"
                       " shape at 128 x 64 scale is why the whole-array abutment check is not"
                       " expressible. Filed upstream as klayout-tools#5698.",
        "result": result("tile", tile),
    },
]

print(json.dumps({
    "schema_version": 1,
    "record_command": "./layout/reports/generate-array-check.sh",
    "issue": 160,
    "check": "klt array-check -- structural regularity of the committed array",
    "array": {
        "top_cell": "macro",
        "bitcell_placements": 8192,
        "rows": 128,
        "columns": 64,
        "hierarchy": "macro -> 32 x bit_slice (x pitch 5.74 um) -> 2 x bl_pair (x=0 R0, x=5.74 M90)"
                     " -> 128 x bitcell (mirrored-pair y pitch 7.21 um, alternating R0/M0)",
    },
    "status": "characterized",
    "summary": {
        "clean": [i["name"] for i in invocations if i["result"]["status"] == "clean"],
        "characterized": [i["name"] for i in invocations if i["result"]["status"] != "clean"],
        "abutment_configurations_clean": 2,
        "symmetry_residuals": 8,
    },
    "not_covered": [
        "Connectivity: array-check is purely geometric. It says nothing about whether the abutting"
        " risers are electrically joined -- that is macro-record-decoder.json and #30 (LVS).",
        "Design rules: no DRC. layout/reports/drc-macro.json is the DRC record.",
        "The array as a whole: the abutment check is one-dimensional, so no invocation covers the"
        " 128 x 64 array in one pass. The two clean runs cover one column along y and the 32 slices"
        " along x; nothing checks the two axes jointly (klayout-tools#5698).",
        "A blanket --tolerance is symmetric: the 0.27 um / 0.48 um above would equally mask a real"
        " gap or overlap up to the same size at a seam. The tolerances are justified by measurement,"
        " not by the check.",
        "The periphery: only bitcell, bl_pair and bit_slice placements are checked.",
    ],
    "upstream_tool_gaps": {
        "2AMLogic/klayout-tools#5698": "1-D abutment model for a 2-D array; no shared-edge/expected-overlap"
                                     " concept distinct from a measurement tolerance; `array-check"
                                     " --format json` omits the provenance block its sibling verbs emit",
    },
    "invocations": invocations,
    "provenance": {
        "klt_version": env["klt_version"],
        "klt_reinstall_spec": f"uvx --from {pin} klt",
        "klayout_version": env["klayout_version"],
        "pdk": None,
        "deck": None,
        "note": "array-check is deck-independent (purely geometric: no PDK deck, no compact models, no"
                " SPICE). klt emits no provenance block for this verb, so this block is added by"
                " ./layout/reports/generate-array-check.sh from `klt env-provenance emit`; its"
                " host_id/os/python_version fields are dropped so the record reproduces on any host.",
        "inputs": {
            macro: sha(macro),
            tile: sha(tile),
            CLIP_LABEL: sha(f"{work}/bl_pair.gds"),
        },
    },
}, indent=2))
PYEOF

echo "record written to $OUT"

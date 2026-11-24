#!/usr/bin/env bash
# Mint the array-regularity evidence record (issue #160) or check the committed one
# (issues #247, #249): run `klt array-check` on the committed macro and on the 2x2
# bitcell tile, then write layout/reports/array-check-macro.json -- or, with
# `--check`, leave the committed record untouched and assert it still reproduces
# (both abutment configurations clean, the symmetry characterization including its
# per-layer residual counts, every invocations[].command string rebuilt from the
# invocation table below, every provenance input hash, no home-directory-shaped
# absolute path). `layout/verify.sh` step 10 is exactly that
# `--check` call: one script owns the invocations, the assertions and the exit-code
# handling in both modes, so the mint and the check cannot drift apart. Nothing is
# regenerated and no existing report is rewritten -- this reads the committed GDS
# only. Run from anywhere:
#
#     ./layout/reports/generate-array-check.sh            # mint the record
#     ./layout/reports/generate-array-check.sh --check    # verify the committed record
#
# Records are append-only evidence: a re-run after a layout or klt change is a new result -- commit
# it as such and say why in the commit message. In particular the record pins the sha256 of
# layout/sram_256x32/macro.gds; if the generator ever re-emits that file, this record is NOT edited,
# a changed array mints a new result.
#
# Two deliberate klt pins live in this repo, for different purposes -- do not "unify" them:
#   * klayout-tools==0.9.2 (KLT_VERSION in .github/workflows/*.yml, attest/*.envelope.json) is the
#     signoff pin.
#   * klayout-tools==0.9.1 (this script) is the report pin: it is the release recorded in the
#     committed report's provenance (provenance.klt_version in layout/reports/array-check-macro.json),
#     so a re-run reproduces the committed record with the same released tool that minted it. See #155.
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

MODE=""
[[ "${1:-}" == "--check" ]] && { MODE="--check"; shift; }
[[ $# -eq 0 ]] || { echo "usage: $0 [--check]" >&2; exit 2; }

KLT_PIN="klayout-tools==0.9.1"
K=(uvx --from "$KLT_PIN" klt)

# Invocation table (issue #249): the single source for every klt array-check
# argument this script passes. The live run() calls below read it through the T
# map, and both python blocks receive it whole and rebuild the recorded
# invocations[].command strings from it -- the mint writes them, and --check
# asserts the committed record's copies byte-for-byte. An argument edited here
# without re-minting layout/reports/array-check-macro.json therefore fails
# --check: a tolerance can no longer be retuned unnoticed. Flat key=value lines,
# parsed into T below and handed to python as one argv; no value contains '='.
TABLE='macro=layout/sram_256x32/macro.gds
tile=layout/bitcell/sg13g2_sram_bitcell_tile2x2.gds
clip_cell=bl_pair
clip_out=bl_pair.gds
slice.name=macro-slice-abutment
slice.cell=bit_slice
slice.pitch=5.74
slice.count=32
slice.direction=x
slice.tolerance=0.48
column.name=macro-column-abutment
column.clip=true
column.cell=bitcell
column.pitch=3.605
column.count=128
column.direction=y
column.tolerance=0.27
sym.name=column-translation-symmetry
sym.clip=true
sym.cell=bl_pair
sym.translate=0,7.21
sym.layers=[[1,0],[5,0],[8,0],[10,0]]
tile2x2.name=tile2x2-abutment-limitation
tile2x2.cell=bitcell_leaf
tile2x2.pitch=2.87
tile2x2.count=2
tile2x2.direction=x'
declare -A T=()
while IFS='=' read -r k v; do
  case "$k" in ''|'#'*) ;; *) T["$k"]="$v" ;; esac
done <<<"$TABLE"

MACRO="${T[macro]}"
TILE="${T[tile]}"
OUT=layout/reports/array-check-macro.json

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# `array-check`'s abutment mode is one-dimensional: pointed at the whole macro with --cell bitcell
# it finds all 8192 placements (every column at once) while measuring array length along a single
# column, so `length == count x pitch` is unsatisfiable at any pitch/count. Clipping one column out
# is the only way to scope the abutment check to one axis today (klayout-tools#5698).
"${K[@]}" clip "$MACRO" --cell "${T[clip_cell]}" -o "$WORK/${T[clip_out]}" > /dev/null

# array-check exits 3 on `violated` -- a successful run with findings, not an error. Capture it.
run() { # run <out.json> <args...>
  local out="$1"; shift
  local rc=0
  "${K[@]}" array-check "$@" --format json > "$out" || rc=$?
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 3 ]; then
    echo "FAIL: klt array-check exited $rc" >&2; exit "$rc"
  fi
}

run "$WORK/slice.json"    "$MACRO"               --cell "${T[slice.cell]}"   --pitch "${T[slice.pitch]}"  --count "${T[slice.count]}"  --direction "${T[slice.direction]}" --tolerance "${T[slice.tolerance]}"
run "$WORK/column.json"   "$WORK/${T[clip_out]}" --cell "${T[column.cell]}"  --pitch "${T[column.pitch]}" --count "${T[column.count]}" --direction "${T[column.direction]}" --tolerance "${T[column.tolerance]}"
run "$WORK/symmetry.json" "$WORK/${T[clip_out]}" --cell "${T[sym.cell]}"     --translate "${T[sym.translate]}" --layers "${T[sym.layers]}"
run "$WORK/tile.json"     "$TILE"                --cell "${T[tile2x2.cell]}" --pitch "${T[tile2x2.pitch]}" --count "${T[tile2x2.count]}" --direction "${T[tile2x2.direction]}"

# scan exits 3 when it finds a home-directory-shaped absolute path; report that rather than
# letting `set -e` abort silently.
scan_ok() { # scan_ok <record.json>
  local rc=0
  "${K[@]}" env-provenance scan "$1" > /dev/null || rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "PASS: no home-directory-shaped absolute path in $1"
  else
    echo "FAIL: $1 carries a home-directory-shaped absolute path:" >&2
    "${K[@]}" env-provenance scan "$1" || true
    return 1
  fi
}

if [ -n "$MODE" ]; then
python3 -I - "$WORK" "$OUT" "$TABLE" <<'CHEOF'
import hashlib, json, sys

work, out, table_raw = sys.argv[1:4]
t = dict(line.split("=", 1) for line in table_raw.splitlines() if line.strip() and not line.lstrip().startswith("#"))
load = lambda n: json.load(open(f"{work}/{n}.json"))
rec = json.load(open(out))
inv = {i["name"]: i for i in rec["invocations"]}

# Rebuild every invocations[].command from the same table that drove the live
# run() calls (issue #249), so an argument -- above all a tolerance -- edited in
# this script without re-minting fails here instead of silently re-running at
# the recorded value.
def command_for(key):
    e = {k[len(key) + 1:]: v for k, v in t.items() if k.startswith(key + ".")}
    label = {"slice": t["macro"], "tile2x2": t["tile"]}.get(key, f"<work>/{t['clip_out']}")
    s = f"klt array-check {label} --cell {e['cell']}"
    if "pitch" in e:
        s += f" --pitch {e['pitch']} --count {e['count']} --direction {e['direction']}"
        if "tolerance" in e:
            s += f" --tolerance {e['tolerance']}"
    if "translate" in e:
        s += f" --translate '{e['translate']}' --layers '{e['layers']}'"
    if e.get("clip") == "true":
        s = (f"klt clip {t['macro']} --cell {t['clip_cell']}"
             f" -o <work>/{t['clip_out']} && {s}")
    return e["name"], s + " --format json"

want_cmds = dict(command_for(k) for k in ("slice", "column", "sym", "tile2x2"))
if sorted(inv) != sorted(want_cmds):
    sys.exit(f"FAIL: record invocations {sorted(inv)} do not match the invocation table"
             f" {sorted(want_cmds)} -- mint a new record")
for name, want in want_cmds.items():
    if inv[name]["command"] != want:
        sys.exit(f"FAIL: {name} documents\n  {inv[name]['command']}\nbut this run used\n  {want}\n"
                 "-- an argument changed in generate-array-check.sh without"
                 " re-minting the record")
print(f"PASS: all {len(want_cmds)} recorded invocations[].command strings match"
      " the arguments this run used")

# The two abutment configurations are assertions: a non-clean status fails the check. Their
# tolerances are the measured shared-edge overlap of mirror abutment, not slack -- read the
# tolerance_rationale in the record before touching them.
for n, name in (("slice", "macro-slice-abutment"), ("column", "macro-column-abutment")):
    st = load(n)["status"]
    if st != "clean":
        sys.exit(f"FAIL: abutment {name} reports status '{st}', expected clean")
    print(f"PASS: abutment {name} is clean")

# The symmetry run is a *characterized* result, not a pass: 8 residuals at the finite-array end
# and at seam 0, both documented in the record. Assert the recorded count and y bands so a change
# that breaks interior symmetry fails here instead of being absorbed. Do NOT raise --tolerance
# to make this report clean.
want = inv["column-translation-symmetry"]["characterization"]
got = load("symmetry")
bands = [tuple(b) for b in want["y_bands_um"]]
if got["violation_count"] != want["residual_count"]:
    sys.exit(f"FAIL: {got['violation_count']} symmetry residuals, record says {want['residual_count']}"
             " -- interior symmetry may have changed; mint a new record deliberately,"
             " do not retune tolerance")
stray = [v["bbox"] for v in got["violations"]
         if not any(lo - 1e-6 <= v["bbox"]["bottom"] and v["bbox"]["top"] <= hi + 1e-6
                    for lo, hi in bands)]
if stray:
    sys.exit(f"FAIL: {len(stray)} symmetry residual(s) outside the recorded y bands {bands}: {stray}")
# Per-layer residual counts (issue #249): each violation reports its layer, so a
# redistribution across layers that kept the total at 8 inside the recorded
# bands cannot slip through either. Recorded zero-count layers (5/0) must stay
# at zero; residuals on unrecorded layers fail.
live_by_layer = {}
for v in got["violations"]:
    live_by_layer[v["layer"]] = live_by_layer.get(v["layer"], 0) + 1
for layer, n in want["by_layer"].items():
    if live_by_layer.get(layer, 0) != n:
        sys.exit(f"FAIL: {live_by_layer.get(layer, 0)} symmetry residuals on layer {layer},"
                 f" record says {n} -- mint a new record deliberately")
extra = sorted(set(live_by_layer) - set(want["by_layer"]))
if extra:
    sys.exit(f"FAIL: symmetry residuals on unrecorded layers {extra}:"
             f" {[(l, live_by_layer[l]) for l in extra]}")
print(f"PASS: {got['violation_count']} symmetry residuals, all within the recorded y bands {bands}"
      f" and per-layer counts {want['by_layer']} (finite-array end + seam 0)")

# Every provenance input hash must match: the committed GDS files directly, and the derived
# bl_pair clip re-clipped from the committed macro.gds by this very run. provenance.klayout_version
# is deliberately not compared: it floats when PyPI ships a newer klayout wheel under
# uvx --from klayout-tools==0.9.1.
for path, want_hash in rec["provenance"]["inputs"].items():
    p = f"{work}/{t['clip_out']}" if path.startswith("(derived)") else path
    got = "sha256:" + hashlib.sha256(open(p, "rb").read()).hexdigest()
    if got != want_hash:
        sys.exit(f"FAIL: {path} differs from {out}"
                 " -- the array changed, so mint a new record (records are append-only)")
print(f"PASS: {out} pins the committed GDS inputs (including the derived bl_pair clip)")
CHEOF
scan_ok "$OUT"
echo "PASS: $OUT reproduces against the committed inputs (generate-array-check.sh --check)"
exit 0
fi

"${K[@]}" env-provenance emit --path macro="$MACRO" --path tile="$TILE" --format json > "$WORK/env.json"

# Mint to a temp file and scan it before replacing the committed record -- a failed or dirty
# mint must not touch it (same contract as generate-erc-macro.sh).
python3 -I - "$WORK" "$KLT_PIN" "$TABLE" <<'PYEOF' > "$WORK/record.json"
import hashlib, json, sys

work, pin, table_raw = sys.argv[1:4]
t = dict(line.split("=", 1) for line in table_raw.splitlines() if line.strip() and not line.lstrip().startswith("#"))
macro, tile = t["macro"], t["tile"]
sha = lambda p: "sha256:" + hashlib.sha256(open(p, "rb").read()).hexdigest()
load = lambda n: json.load(open(f"{work}/{n}.json"))
env = load("env")

SYM_COUNT = 8
SYM_BANDS = [[7.065, 7.355], [461.440, 461.585]]
SYM_BY_LAYER = {"1/0": 2, "8/0": 4, "10/0": 2, "5/0": 0}

# The same builder --check uses (issue #249): the minted invocations[].command
# strings and the strings --check rebuilds and compares come from one table.
def command_for(key):
    e = {k[len(key) + 1:]: v for k, v in t.items() if k.startswith(key + ".")}
    label = {"slice": t["macro"], "tile2x2": t["tile"]}.get(key, f"<work>/{t['clip_out']}")
    s = f"klt array-check {label} --cell {e['cell']}"
    if "pitch" in e:
        s += f" --pitch {e['pitch']} --count {e['count']} --direction {e['direction']}"
        if "tolerance" in e:
            s += f" --tolerance {e['tolerance']}"
    if "translate" in e:
        s += f" --translate '{e['translate']}' --layers '{e['layers']}'"
    if e.get("clip") == "true":
        s = (f"klt clip {t['macro']} --cell {t['clip_cell']}"
             f" -o <work>/{t['clip_out']} && {s}")
    return e["name"], s + " --format json"

cmds = dict(command_for(k) for k in ("slice", "column", "sym", "tile2x2"))

# Mint-time assertions (issue #247): check the run results against the expectations this record
# stamps before writing it, so an abutment or interior-symmetry regression fails the mint instead
# of being recorded as if expected.
for n, name in (("slice", "macro-slice-abutment"), ("column", "macro-column-abutment")):
    st = load(n)["status"]
    if st != "clean":
        sys.exit(f"FAIL: abutment {name} reports status '{st}', expected clean")
sym = load("symmetry")
if sym["violation_count"] != SYM_COUNT:
    sys.exit(f"FAIL: {sym['violation_count']} symmetry residuals, expected {SYM_COUNT}"
             " -- interior symmetry may have changed; mint deliberately, do not retune tolerance")
stray = [v["bbox"] for v in sym["violations"]
         if not any(lo - 1e-6 <= v["bbox"]["bottom"] and v["bbox"]["top"] <= hi + 1e-6
                    for lo, hi in SYM_BANDS)]
if stray:
    sys.exit(f"FAIL: {len(stray)} symmetry residual(s) outside the characterized y bands"
             f" {SYM_BANDS}: {stray}")
live_by_layer = {}
for v in sym["violations"]:
    live_by_layer[v["layer"]] = live_by_layer.get(v["layer"], 0) + 1
for layer, n in SYM_BY_LAYER.items():
    if live_by_layer.get(layer, 0) != n:
        sys.exit(f"FAIL: {live_by_layer.get(layer, 0)} symmetry residuals on layer {layer},"
                 f" expected {n} -- interior symmetry may have changed; mint deliberately")
extra = sorted(set(live_by_layer) - set(SYM_BY_LAYER))
if extra:
    sys.exit(f"FAIL: symmetry residuals on uncharacterized layers {extra}:"
             f" {[(l, live_by_layer[l]) for l in extra]}")

# The clipped column is a derived intermediate in a mktemp dir; klt records its absolute path in
# `file`. Replace that with a stable logical name so the record is byte-for-byte reproducible, and
# pin the intermediate by content hash instead.
CLIP_LABEL = f"(derived) {t['clip_cell']} column clipped from {t['macro']}"
def result(name, source):
    r = load(name)
    if source == CLIP_LABEL:
        r["file"] = CLIP_LABEL
    return r

invocations = [
    {
        "name": "macro-slice-abutment",
        "intent": "the 32 bit_slice columns abut along x at the slice pitch",
        "command": cmds["macro-slice-abutment"],
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
        "command": cmds["macro-column-abutment"],
        "input": CLIP_LABEL,
        "input_content_hash": sha(f"{work}/{t['clip_out']}"),
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
        "command": cmds["column-translation-symmetry"],
        "input": CLIP_LABEL,
        "input_content_hash": sha(f"{work}/{t['clip_out']}"),
        "input_derived_from": {macro: sha(macro)},
        "expectation": "characterized: 8 residuals in exactly two y bands, both explained below."
                       " NOT a pass, and NOT to be tolerance-tuned away -- raising --tolerance until"
                       " this reports clean would mask a future break of interior symmetry. The"
                       " residual count and the two bands are the regression guard.",
        "characterization": {
            "residual_count": SYM_COUNT,
            "y_bands_um": SYM_BANDS,
            "by_layer": SYM_BY_LAYER,
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
        "command": cmds["tile2x2-abutment-limitation"],
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
        "symmetry_residuals": SYM_COUNT,
    },
    "not_covered": [
        "Connectivity: array-check is purely geometric. It says nothing about whether the abutting"
        " risers are electrically joined -- that is macro-record-blbm.json and #30 (LVS).",
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
            CLIP_LABEL: sha(f"{work}/{t['clip_out']}"),
        },
    },
}, indent=2))
PYEOF
scan_ok "$WORK/record.json"
mv "$WORK/record.json" "$OUT"
echo "record written to $OUT"

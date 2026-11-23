#!/usr/bin/env bash
# Mint the as-built klt erc report of the macro (issue #229): run `klt erc` on the
# committed macro.gds against macro.supply.json at the klt version pinned for
# signoff (KLT_VERSION in .github/workflows/signoff.yml; the report's provenance
# records it) and write layout/reports/erc-macro.json. `layout/verify.sh` step 11
# checks this report against the committed inputs (`klt erc --check`), and
# test_erc_controls.py reads it as the as-built baseline of the negative controls.
#
# --omit-antenna-tables is part of the record, not a convenience: without a --pdk
# every antenna verdict is 'unchecked', and the all-ungraded gates[] table of the
# 17,269 gate nets is ~45 MB of JSON; omitting it (klayout-tools #3011's exact
# purpose) keeps every finding, every verdict and the exit code identical while
# making the report committable (1.3 MB). Records are append-only evidence: a
# re-run after a layout or klt change is a new result -- commit it as such and say
# why in the commit message. Run from anywhere:
#
#     ./layout/reports/generate-erc-macro.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
D=layout/sram_256x32
KLT_VERSION="$(sed -n 's/^  KLT_VERSION: "\(.*\)"$/\1/p' .github/workflows/signoff.yml)"
[ -n "$KLT_VERSION" ] || { echo "cannot read KLT_VERSION from .github/workflows/signoff.yml"; exit 1; }

uv run --with klayout python3 $D/supply_spec.py
if git diff --quiet -- $D/macro.supply.json; then
  echo "PASS: macro.supply.json matches supply_spec.py output"
else
  echo "FAIL: macro.supply.json differs from supply_spec.py output; commit the regenerated spec"; exit 1
fi

# klt erc exits 3 on findings -- the as-built report is expected to carry them
# (the pin squares are not on the rails, #108); only a tool error fails the mint.
# Write to a sibling temp file and replace the committed report only after an
# accepted exit and a complete JSON result (a failed re-mint must not truncate it).
TMP="$(mktemp layout/reports/.erc-macro.XXXXXX)"
trap 'rm -f "$TMP"' EXIT
rc=0
uvx --from "klayout-tools==$KLT_VERSION" klt erc $D/macro.gds $D/macro.supply.json \
  --top macro --deck sg13g2 --omit-antenna-tables --format json \
  > "$TMP" || rc=$?
if [ "$rc" -ne 0 ] && [ "$rc" -ne 3 ]; then
  echo "FAIL: klt erc exited $rc (previous report left untouched)"; exit "$rc"
fi
python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$TMP" \
  || { echo "FAIL: klt erc output is not complete JSON (previous report left untouched)"; exit 1; }
mv "$TMP" layout/reports/erc-macro.json
trap - EXIT
echo "report written to layout/reports/erc-macro.json (klt erc exit $rc: findings present, as built)"

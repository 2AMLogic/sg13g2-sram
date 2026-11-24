#!/usr/bin/env bash
# Mint the macro DRC evidence of record (issue #251): run `klt drc` on the
# committed macro.gds at the klt version pinned for signoff (KLT_VERSION in
# .github/workflows/signoff.yml; ci.yml pins the same value) -- through `uvx`,
# never the host klt -- and write layout/reports/drc-macro.json. The record is
# the T1 item 3 evidence (manifests/sg13g2-sram.json cites it, pinned to the
# macro GDS hash), so it must be reproducible from the pinned release: a
# worker's dev klt ships an unreleased deck, and a record minted with it cites
# a deck nobody installing the pin has (#251; the pre-#251 record was exactly
# that, re-minted by a host-klt run). `layout/verify.sh` step 8 checks this
# report against the committed layout (`klt drc --check`, cheap hash mode) at
# the same pin, and `klt signoff` quotes its coverage block verbatim into
# manifests/sg13g2-sram.signoff.json -- regenerate that file after a re-mint
# (command in manifests/README.md).
#
# The mint asserts what this record is evidence of before replacing it (same
# contract as generate-array-check.sh, #247): a clean verdict from the released
# deck at the pin, binding the committed macro.gds. A failed, non-clean or
# unreleased-deck mint leaves the committed report untouched. Records are
# append-only evidence: a re-run after a layout or klt change is a new
# result -- commit it as such and say why in the commit message.
#
# provenance.klayout_version floats: `uvx` resolves the klayout wheel fresh, so
# a newer PyPI release can change that one field between runs (the same caveat
# generate-array-check.sh's --check mode carries). Everything else in the
# record is byte-stable for unchanged inputs. Run from anywhere:
#
#     ./layout/reports/generate-drc-macro.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
D=layout/sram_256x32
KLT_VERSION="$(sed -n 's/^  KLT_VERSION: "\(.*\)"$/\1/p' .github/workflows/signoff.yml)"
[ -n "$KLT_VERSION" ] || { echo "cannot read KLT_VERSION from .github/workflows/signoff.yml"; exit 1; }

# klt drc exits 3 on violations -- this record is evidence of a *clean* DRC, so
# a findings run fails the mint instead of being committed as if clean. Write to
# a sibling temp file and replace the committed report only after an accepted
# exit and a complete JSON result (a failed re-mint must not truncate it).
TMP="$(mktemp layout/reports/.drc-macro.XXXXXX)"
trap 'rm -f "$TMP"' EXIT
rc=0
uvx --from "klayout-tools==$KLT_VERSION" klt drc --deck sg13g2 --top macro $D/macro.gds \
  --format json > "$TMP" || rc=$?
if [ "$rc" -ne 0 ]; then
  echo "FAIL: klt drc exited $rc (previous report left untouched)"; exit "$rc"
fi
python3 -I - "$TMP" "$KLT_VERSION" "$D/macro.gds" <<'PYEOF'
import hashlib, json, sys

report, pin, gds = sys.argv[1:4]
r = json.load(open(report))  # incomplete JSON fails the mint; record left untouched
p = r["provenance"]
if r.get("status") != "clean" or r.get("violation_count") != 0:
    sys.exit(f"FAIL: drc reports {r.get('status')} with {r.get('violation_count')} violation(s)"
             " -- fix the layout; this record is evidence of a clean DRC")
if p["klt_version"] != pin:
    sys.exit(f"FAIL: report minted by klt {p['klt_version']}, expected the pin {pin}")
if not p["deck"]["released"]:
    sys.exit(f"FAIL: deck {p['deck']['name']} {p['deck']['content_hash']} is unreleased --"
             " the record must cite the released deck the pin ships (#251)")
want = "sha256:" + hashlib.sha256(open(gds, "rb").read()).hexdigest()
if p["input"]["content_hash"] != want:
    sys.exit(f"FAIL: report binds input {p['input']['content_hash']}, not {gds} ({want})")
print(f"PASS: clean, klt {p['klt_version']}, released deck {p['deck']['content_hash'][:19]}…,"
      f" input {p['input']['content_hash'][:19]}…")
PYEOF
mv "$TMP" layout/reports/drc-macro.json
trap - EXIT
echo "report written to layout/reports/drc-macro.json"

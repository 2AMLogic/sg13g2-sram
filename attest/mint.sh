#!/usr/bin/env bash
# Mint a T1 attestation envelope in this directory (issue #155). Run from
# anywhere:   ./attest/mint.sh 10
#
# Envelopes are append-only evidence: never hand-edit one to change a result.
# A re-mint after a change to a path the inventory content-hashes is a new
# result -- commit it as such and say why in the commit message (git history is
# the trail). CI only ever `--check`s these envelopes; it must never re-sign
# them, because a gate that re-signs itself is not a gate.
#
# WHY THIS ALWAYS ROUTES THROUGH uvx AT THE CI PIN, NEVER THE HOST `klt`
# ---------------------------------------------------------------------
# CI grades these envelopes with a pinned klayout-tools (`KLT_VERSION` in
# .github/workflows/ci.yml), so the committed artifact has to be reproducible
# by anyone at that pin. Measured 2026-11-14 against origin/main @ eed93e9, on
# item 10:
#
#   * pinned klt, `-o FILE`              -- reproduces the committed
#     attest/item10.envelope.json byte-identically (`cmp` clean). The envelope
#     carries no timestamp, so the mint is deterministic.
#   * host klt, `-o FILE`                -- the pinned `--check` reports
#     `status: match`, exit 0. It PASSES. What is wrong with it is that it
#     stamps `provenance.klt_version` in a *committed* artifact with an
#     unreleased dev-build string (measured: "0.9.2.dev1024+g8da9718f0cb6"),
#     which nobody can reproduce later. That -- committed-artifact determinism
#     -- is the reason this script refuses the host tool.
#   * host klt, `--format json > FILE`   -- additionally emits a top-level
#     `manifest_entry` block, and the pinned `--check` on that envelope exits 3
#     naming `manifest_entry`. This is the separate foot-gun in the reflex form.
#
# So do NOT read this as "CI rejects any host-klt envelope" -- that claim was
# measured FALSE (the `-o` form passes the pinned check). Two distinct reasons:
# determinism for the `-o` form, an outright rc=3 for `--format json >`.
# Hence: `-o`, never `--format json >`; and `uvx --from`, never bare `klt`.
#
# This deliberately diverges from layout/reports/generate.sh, which calls the
# host `klt` directly. That is right for DRC/LVS reports (newest deck wins) and
# wrong here (the artifact is graded at a pin and records the minting version).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Only ever read the pin; a seventh hardcoded copy is exactly the bug.
# ATTEST_MINT_CI_WORKFLOW is a test hook (point it at a copy of ci.yml to
# exercise the unparseable-pin branch) -- not for normal use.
CI_WORKFLOW="${ATTEST_MINT_CI_WORKFLOW:-.github/workflows/ci.yml}"

die() { printf '%s\n' "$@" >&2; exit 1; }

pin_sync_set() {
  cat >&2 <<'EOS'

The klt pin is recorded at 6 sites, which must be kept in sync:
  .github/workflows/ci.yml:10        KLT_VERSION (the one this script reads)
  .github/workflows/signoff.yml:14   KLT_VERSION
  README.md:117                      signoff-record mint invocation
  README.md:125                      item 10 --check invocation
  manifests/README.md:8              grading invocation
  manifests/README.md:13             the "Bump both together" prose
Line numbers are as of origin/main @ eed93e9 -- re-grep before relying on them.
EOS
}

# Why items 1, 9 and 2 cannot be minted here, and the one thing that lifts it.
UNLOCK_NOTE="$(cat <<'EOS'
What would lift this: a klayout-tools *release* carrying `--skip-local-only`.
The flag landed upstream in 2AMLogic/klayout-tools#5209 but has not shipped in
a wheel -- it is absent from the 0.8.0 pin and from 0.9.1, the latest release
on PyPI (a 0.9.1 mint with the flag exits 2, unknown option). The release gap
is filed as 2AMLogic/klayout-tools#5694. Once it lands, items 1 and 9 can be
minted above the gate pin and still graded at it -- which is already accepted
practice in this repo: manifests/README.md:5 records that
attest/item2.envelope.json was "produced with `klt signoff --attest 2` from
klayout-tools `ce6583fe`, which 0.8.0 lacks but 0.8.0 grades".
EOS
)"

usage() {
  cat >&2 <<'EOS'
usage: ./attest/mint.sh <item>

Mints attest/item<item>.envelope.json with the CI-pinned klayout-tools.

  10   mint the repo-hygiene envelope (the only item mintable at the pin)
  1    refuses -- 25 local_only inventory entries need the PDK
  2    refuses -- no attest/item2.json inventory exists
  9    refuses -- its cold start is a 6-hour fleet grid

There is deliberately no "mint everything" mode: each envelope is evidence,
and a blanket re-sign is how an unreviewed result gets committed.
EOS
  exit 2
}

[ "$#" -eq 1 ] || usage
ITEM="$1"

case "$ITEM" in
  1)
    die "refusing to mint item 1 at the pin." \
        "" \
        "attest/item1.json has 25 inventory entries marked local_only: true --" \
        "\`design/netlist.sh --check <block>\` freshness commands that need the" \
        "PDK. The 0.8.0 pin has no --skip-local-only, so its generate path runs" \
        "all of them; on a host without the PDK that cannot succeed, and the" \
        "pin's --check path is what correctly skips them today (which is why CI" \
        "stays green). Nothing was launched and no file was written." \
        "" \
        "$UNLOCK_NOTE"
    ;;
  2)
    die "refusing to mint item 2: there is no inventory to mint from." \
        "" \
        "attest/item2.envelope.json exists but attest/item2.json does not, so" \
        "there is no --inventory argument to give. Per manifests/README.md:5" \
        "that envelope was produced with \`klt signoff --attest 2\` from" \
        "klayout-tools commit ce6583fe -- an unreleased build that 0.8.0 grades" \
        "but does not contain. Re-minting it is out of scope for this script;" \
        "reconstructing the missing inventory is a spec question for spec/," \
        "not a side effect of a mint. Nothing was launched, no file written." \
        "" \
        "$UNLOCK_NOTE"
    ;;
  9)
    die "refusing to mint item 9 at the pin." \
        "" \
        "attest/item9.json's cold_start entry is local_only: true with" \
        "argv [\"sim/run_all.sh\"] and timeout_s 21600 -- a 6-hour, 45-corner" \
        "run that goes to the batch fleet. The 0.8.0 pin has no" \
        "--skip-local-only, so its generate path would launch it (measured: it" \
        "does so even under CI=true / GITHUB_ACTIONS=true). This script will" \
        "not submit a fleet grid as a side effect of a re-sign." \
        "" \
        "The standing operator ruling r7-q17 (2026-11-06, on PR #130) is that" \
        "a correct PR whose only red check is an attestation it staled is" \
        "finished by re-attesting under the pinned toolchain. For item 9 that" \
        "is not yet possible -- escalate rather than minting around it." \
        "Nothing was launched and no file was written." \
        "" \
        "$UNLOCK_NOTE"
    ;;
  10)
    : # the one mintable item; handled below
    ;;
  *)
    die "unknown attestation item: '$ITEM'" \
        "" \
        "Mintable: 10. Known-but-refused: 1, 2, 9 (run this script with one of" \
        "those for the measured reason). No file was written."
    ;;
esac

INVENTORY="attest/item${ITEM}.json"
ENVELOPE="attest/item${ITEM}.envelope.json"
[ -f "$INVENTORY" ] || die "inventory not found: $INVENTORY"

[ -f "$CI_WORKFLOW" ] || {
  printf '%s\n' "cannot read the klt pin: $CI_WORKFLOW does not exist." >&2
  pin_sync_set
  exit 1
}

PIN="$(sed -n \
  's/^[[:space:]]*KLT_VERSION:[[:space:]]*"\([^"]\{1,\}\)"[[:space:]]*$/\1/p' \
  "$CI_WORKFLOW" | head -n 1)"

[ -n "$PIN" ] || {
  printf '%s\n' \
    "cannot parse KLT_VERSION from $CI_WORKFLOW -- refusing to mint rather" \
    "than falling back to a default pin, which would silently commit an" \
    "envelope graded against a version nobody declared." >&2
  pin_sync_set
  exit 1
}

# -o into a temp file, then mv: a failed mint must not leave a truncated
# envelope behind. (klt's -o already writes nothing on exit 3 --
# 2AMLogic/klayout-tools#5538 -- so this is belt-and-braces, and cheap.)
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "minting $ENVELOPE with klayout-tools==$PIN (pin from $CI_WORKFLOW)" >&2
uvx --from "klayout-tools==$PIN" klt signoff --attest "$ITEM" \
  --inventory "$INVENTORY" -o "$WORK/envelope.json"

mv "$WORK/envelope.json" "$ENVELOPE"
echo "wrote $ENVELOPE" >&2
echo "verify with: uvx --from \"klayout-tools==$PIN\" klt signoff --attest $ITEM --inventory $INVENTORY --check $ENVELOPE" >&2

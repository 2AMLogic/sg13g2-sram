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

# The old unlock note here -- "waiting on a klayout-tools *release* carrying
# --skip-local-only", filed as 2AMLogic/klayout-tools#5694 -- is RESOLVED:
# 0.9.2 shipped the flag (#5209). Items 1 and 9 mint again through the
# refresh path below. The flag requires --attest plus -o and carries each
# skipped local_only command's committed outcome from the existing envelope,
# so it is a refresh of committed evidence, never a cold mint. Minting above
# the gate pin remains accepted practice in this repo, per
# manifests/README.md:5: attest/item2.envelope.json is minted with
# `klt signoff --attest 2 --input` from the released 0.9.1 (the release that
# first shipped that flag combination) and graded met at 0.8.0.

usage() {
  cat >&2 <<'EOS'
usage: ./attest/mint.sh <item>

Mints attest/item<item>.envelope.json with the CI-pinned klayout-tools.

  1    refresh-mints the design-checks envelope (--skip-local-only carries
       the 25 local_only entries' committed outcomes; no PDK needed)
  2    refuses -- the CI pin cannot mint item 2 (0.9.1 can; see the message)
  9    refresh-mints the sim envelope (--skip-local-only skips the fleet
       cold start, carrying its committed outcome; no fleet submit)
  10   mints the repo-hygiene envelope

There is deliberately no "mint everything" mode: each envelope is evidence,
and a blanket re-sign is how an unreviewed result gets committed.
EOS
  exit 2
}

[ "$#" -eq 1 ] || usage
ITEM="$1"

case "$ITEM" in
  1|9|10)
    : # mintable below; 1 and 9 refresh through the --skip-local-only path
    ;;
  2)
    die "refusing to mint item 2: this script pins the CI klt, and the pin" \
        "cannot mint item 2." \
        "" \
        "attest/item2.json does not exist, so there is no --inventory to give;" \
        "and the pin's --attest documents only the --inventory form -- the" \
        "--input STREAM mint path for item 2 first shipped in the released" \
        "0.9.1 (measured, issue #159: a 0.9.1 mint of item 2 from the committed" \
        "macro.gds reproduces and grades met at the gate pin). Re-mint item 2" \
        "above the pin, as manifests/README.md:5 records:" \
        "" \
        "  uvx --from \"klayout-tools==0.9.1\" klt signoff --attest 2 \\" \
        "    --input layout/sram_256x32/macro.gds \\" \
        "    --generator \"uv run --with klayout python3 layout/sram_256x32/generate.py\" \\" \
        "    --regenerated-hash sha256:<macro.gds sha256> -o attest/item2.envelope.json" \
        "" \
        "Nothing was launched, no file written."
    ;;
  *)
    die "unknown attestation item: '$ITEM'" \
        "" \
        "Mintable: 1, 9 (refresh-only, --skip-local-only) and 10." \
        "Known-but-refused: 2 (run this script with it for the measured" \
        "reason). No file was written."
    ;;
esac

INVENTORY="attest/item${ITEM}.json"
ENVELOPE="attest/item${ITEM}.envelope.json"
[ -f "$INVENTORY" ] || die "inventory not found: $INVENTORY"

# 0.9.2's --skip-local-only (2AMLogic/klayout-tools#5209, shipped in the
# 0.9.2 release; the release gap tracked as #5694 is thereby closed) does not
# run the inventory's local_only commands: it requires --attest plus -o and
# carries each skipped command's committed outcome from the existing envelope
# (recorded as skipped_checks / "[SKIP] ... committed outcome: pass"). That
# makes it a REFRESH of committed evidence, never a cold mint -- with no
# committed envelope there is nothing to carry outcomes from, so the refusal
# below states that distinction instead of silently minting a hollow one.
if grep -q '"local_only": true' "$INVENTORY"; then
  [ -f "$ENVELOPE" ] || die "refusing to cold-mint item $ITEM." \
      "" \
      "attest/item${ITEM}.json carries local_only entries, so this script" \
      "passes --skip-local-only -- and that flag requires -o to point at an" \
      "existing envelope, whose committed outcomes it carries for the skipped" \
      "commands. With no committed envelope there is nothing to carry from," \
      "so a cold mint here would be an evidence-less one: mint item $ITEM" \
      "once on a host that can run its local_only commands, commit that" \
      "envelope, and refresh it here afterwards. Nothing was launched and no" \
      "file was written."
  SKIP_LOCAL_ONLY=(--skip-local-only)
else
  SKIP_LOCAL_ONLY=()
fi

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
# On the --skip-local-only refresh path the -o file is ALSO the source of the
# committed outcomes carried for skipped local_only commands, so the temp is
# seeded with the committed envelope's bytes first: identical outcomes, and a
# failed refresh still leaves the committed envelope untouched.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ ${#SKIP_LOCAL_ONLY[@]} -gt 0 ]; then
  cp "$ENVELOPE" "$WORK/envelope.json"
fi

echo "minting $ENVELOPE with klayout-tools==$PIN (pin from $CI_WORKFLOW)" >&2
uvx --from "klayout-tools==$PIN" klt signoff --attest "$ITEM" \
  --inventory "$INVENTORY" ${SKIP_LOCAL_ONLY[@]+"${SKIP_LOCAL_ONLY[@]}"} \
  -o "$WORK/envelope.json"

mv "$WORK/envelope.json" "$ENVELOPE"
echo "wrote $ENVELOPE" >&2
echo "verify with: uvx --from \"klayout-tools==$PIN\" klt signoff --attest $ITEM --inventory $INVENTORY --check $ENVELOPE" >&2

#!/usr/bin/env bash
# Tests for attest/mint.sh's local_only detection (issue #211).
# Runs mint.sh from a temporary copy of the repo with `uvx` stubbed to record
# its argument vector, so nothing is minted and no fleet job is submitted.
#   ./attest/test_mint.sh
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILS=0

ok()   { printf 'ok   %s\n' "$1"; }
fail() { printf 'FAIL %s\n' "$1"; FAILS=$((FAILS + 1)); }

mkdir -p "$TMP/bin"
cat >"$TMP/bin/uvx" <<'EOS'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$STUB_LOG"
# Behave like a successful mint: write the -o target.
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then echo '{"minted":true}' >"$2"; fi
  shift
done
EOS
chmod +x "$TMP/bin/uvx"

# fresh_root NAME -> sets R to a fresh copy with attest/, the CI workflow.
fresh_root() {
  R="$TMP/$1"
  mkdir -p "$R/attest" "$R/.github/workflows"
  cp "$SRC/attest/mint.sh" "$R/attest/"
  cp "$SRC/.github/workflows/ci.yml" "$R/.github/workflows/"
  : >"$TMP/stub.log"
  export STUB_LOG="$TMP/stub.log"
}

run_mint() { # item [PATH override]
  PATH="${2:-$TMP/bin:$PATH}" "$R/attest/mint.sh" "$1" >"$TMP/out" 2>&1
}

calls() { wc -l <"$STUB_LOG" | tr -d ' '; }

# 1. pretty and compact inventories both pass --skip-local-only (item 9 layout)
for form in pretty compact; do
  fresh_root "i9-$form"
  cp "$SRC/attest/item9.json" "$R/attest/"
  echo '{"old":true}' >"$R/attest/item9.envelope.json"
  [ "$form" = compact ] && jq -c . "$SRC/attest/item9.json" >"$R/attest/item9.json"
  if run_mint 9 && grep -q -- '--skip-local-only' "$STUB_LOG"; then
    ok "item 9 $form: --skip-local-only passed"
  else fail "item 9 $form: flag missing"; fi
done

# 2. compact inventory with no envelope refuses before the stub runs
fresh_root i9-noenv
jq -c . "$SRC/attest/item9.json" >"$R/attest/item9.json"
if ! run_mint 9 && [ "$(calls)" = 0 ] && [ ! -e "$R/attest/item9.envelope.json" ]; then
  ok "item 9 compact, no envelope: refused, no stub call"
else fail "item 9 compact, no envelope: did not refuse"; fi

# 3. item 1 (nested markers, compact) and item 10 (no-marker control)
fresh_root i1
jq -c . "$SRC/attest/item1.json" >"$R/attest/item1.json"
echo '{"old":true}' >"$R/attest/item1.envelope.json"
if run_mint 1 && grep -q -- '--skip-local-only' "$STUB_LOG"; then
  ok "item 1 compact: flag passed"
else fail "item 1 compact: flag missing"; fi

fresh_root i10
cp "$SRC/attest/item10.json" "$R/attest/"
if run_mint 10 && [ "$(calls)" = 1 ] && ! grep -q -- '--skip-local-only' "$STUB_LOG"; then
  ok "item 10: ordinary mint path, no flag"
else fail "item 10: unexpected arguments"; fi

# 4. false / string "true" are not markers
for v in 'false' '"true"'; do
  fresh_root "i10-$v"
  printf '{"cmds":[{"local_only": %s}]}\n' "$v" >"$R/attest/item10.json"
  if run_mint 10 && ! grep -q -- '--skip-local-only' "$STUB_LOG"; then
    ok "local_only=$v is not a marker"
  else fail "local_only=$v treated as a marker"; fi
done

# 5. malformed / empty inventory, missing parser: nonzero, no stub call,
#    pre-existing envelope untouched
check_refusal() { # label
  if [ "$RC" -ne 0 ] && [ "$(calls)" = 0 ] \
     && [ "$(cat "$R/attest/item9.envelope.json")" = '{"old":true}' ]; then
    ok "$1: refused, no stub call, envelope intact"
  else fail "$1: rc=$RC calls=$(calls)"; fi
}
for bad in 'not json' '' '{"a":'; do
  fresh_root "bad"
  printf '%s' "$bad" >"$R/attest/item9.json"
  echo '{"old":true}' >"$R/attest/item9.envelope.json"
  run_mint 9; RC=$?
  check_refusal "malformed inventory '$bad'"
done

fresh_root nojq
cp "$SRC/attest/item9.json" "$R/attest/"
echo '{"old":true}' >"$R/attest/item9.envelope.json"
# PATH with the stub and only the basic tools, but no jq.
mkdir -p "$TMP/nojq-bin"
for t in bash env cat sed head mktemp rm cp mv dirname wc tr grep; do
  ln -sf "$(command -v "$t")" "$TMP/nojq-bin/$t"
done
cp -p "$TMP/bin/uvx" "$TMP/nojq-bin/uvx"
run_mint 9 "$TMP/nojq-bin"; RC=$?
check_refusal "jq unavailable"
grep -q 'jq is required' "$TMP/out" || fail "jq unavailable: no diagnostic"

[ "$FAILS" -eq 0 ] && echo "all passed" || { echo "$FAILS failed"; exit 1; }

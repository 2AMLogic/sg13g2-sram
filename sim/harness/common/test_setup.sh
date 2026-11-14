#!/usr/bin/env bash
# test_setup.sh -- regression test for the scaffolding shared by every
# sim/*/run_*.sh: sim/harness/common/setup.sh and sim/harness/common/run_klt.sh.
#
# Needs no PDK, no klt, no ngspice and no network, simulates nothing, and
# writes nothing inside the real checkout: every run happens in a throwaway
# copy of the tracked sim/ and design/ trees (records/ and sizing/ excluded, so
# the append-only evidence directories are never read or written) against a
# stub `klt`, a stub `ngspice` and a stub PDK tree.
#
# What it pins:
#   1. The `klt sim` exit-code policy, stated once in run_klt.sh and shared by
#      the single-request and --batch-set submits: 0 and 3 are results, 4 is a
#      result only when the caller tolerates it AND a report exists, anything
#      else is a fleet error and exits 6.
#   2. The same policy as each of the four batch run scripts actually reaches
#      it, end to end, for a stubbed `klt sim` exit of 0, 3, 4 and 5 -- plus
#      run_sizing.sh now REFUSING an exit 4 that produced no envelope, which
#      is the one intentional behaviour change of issue #157.
#   3. new_record's trap ordering: a failure part-way through a series of
#      scratch-request writes leaves no .*.json behind in the checkout.
#   4. The append-only record guard (exit 4) and the fleet-bucket redaction.
#
# Usage: sim/harness/common/test_setup.sh      (quiet unless something fails)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/../../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

FAILED=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1" >&2; FAILED=1; }
check() { # check <description> <expected> <actual>
  if [[ "$2" == "$3" ]]; then pass "$1"; else fail "$1 (expected '$2', got '$3')"; fi
}

# --- stubs --------------------------------------------------------------------
BIN="${TMP}/bin"
mkdir -p "${BIN}"

cat > "${BIN}/klt" <<'STUB'
#!/usr/bin/env bash
# Stub klt. `netlist` always succeeds (netlist freshness is not under test).
# `sim` reports a fleet bucket on stderr (so redaction is exercised), honours
# STUB_KLT_REPORT (write a non-empty --report-out) and STUB_KLT_SIM_STDOUT
# (an envelope on stdout, which is how --batch-set reports), then exits
# STUB_KLT_SIM_RC.
set -uo pipefail
sub="${1:-}"; shift || true
case "${sub}" in
  netlist) exit 0 ;;
  sim)
    echo "stub klt sim: submitted to s3://real-account-id-1234/jobs/stub" >&2
    out=""; prev=""
    for a in "$@"; do
      [[ "${prev}" == "--report-out" ]] && out="${a}"
      prev="${a}"
    done
    if [[ "${STUB_KLT_REPORT:-0}" == 1 && -n "${out}" ]]; then
      mkdir -p "$(dirname "${out}")"
      printf 'stub-report\n' > "${out}"
    fi
    if [[ -n "${STUB_KLT_SIM_STDOUT:-}" ]]; then printf '%s\n' "${STUB_KLT_SIM_STDOUT}"; fi
    exit "${STUB_KLT_SIM_RC:-0}"
    ;;
  *) echo "stub klt: unexpected subcommand '${sub}'" >&2; exit 127 ;;
esac
STUB

cat > "${BIN}/ngspice" <<'STUB'
#!/usr/bin/env bash
# Stub ngspice: converges. Reads the deck's `wrdata <path> i(Vd)` line and
# writes a monotonic Id-Vgs sweep there, then prints an operating point.
set -uo pipefail
if [[ "${1:-}" == "--version" ]]; then echo "ngspice-46 stub"; exit 0; fi
deck="${2:-}"
sweep="$(sed -n 's/^wrdata \([^ ]*\) .*/\1/p' "${deck}" | head -1)"
if [[ -n "${sweep}" ]]; then
  : > "${sweep}"
  for i in $(seq 0 33); do
    python3 -I -c "print(${i}/33.0, 1e-12 + ${i}*3e-5)" >> "${sweep}"
  done
fi
echo "i(Vd) = -1.234560e-04"
exit 0
STUB

# Fault-injecting python3: fails the FAULT_AT'th invocation whose argv contains
# FAULT_MATCH and passes everything else through. Used to kill a run script
# between two scratch-request writes, which is the failure new_record's trap
# ordering has to survive.
REAL_PYTHON3="$(command -v python3)"
cat > "${BIN}/python3" <<STUB
#!/usr/bin/env bash
set -uo pipefail
if [[ -n "\${FAULT_MATCH:-}" && "\$*" == *"\${FAULT_MATCH}"* ]]; then
  n=\$(( \$(cat "\${FAULT_COUNT_FILE}" 2>/dev/null || echo 0) + 1 ))
  echo "\${n}" > "\${FAULT_COUNT_FILE}"
  if [[ "\${n}" == "\${FAULT_AT:-0}" ]]; then
    echo "stub python3: injected failure on match \${n} (\${FAULT_MATCH})" >&2
    exit 9
  fi
fi
exec "${REAL_PYTHON3}" "\$@"
STUB
chmod +x "${BIN}/klt" "${BIN}/ngspice" "${BIN}/python3"

# --- stub PDK tree ------------------------------------------------------------
STUB_PDK="${TMP}/pdk"
NGDIR="${STUB_PDK}/ihp-sg13g2/libs.tech/ngspice"
mkdir -p "${NGDIR}/models" "${NGDIR}/osdi"
for m in psp103 psp103_nqs r3_cmc mosvar; do printf 'stub\n' > "${NGDIR}/osdi/${m}.osdi"; done
for l in cornerMOSlv.lib cornerMOShv.lib; do printf '* stub\n' > "${NGDIR}/models/${l}"; done

# --- sandbox: the tracked sim/ and design/ trees, without the evidence dirs ---
# A fresh copy per run, so no run script can see another's record directory and
# no append-only directory in the real checkout is touched.
new_sandbox() {
  local sb="${TMP}/sb.$1"
  rm -rf "${sb}"; mkdir -p "${sb}"
  # --cached --others: an uncommitted new helper under sim/harness/common/ must
  # be part of the sandbox too, or this test silently exercises nothing.
  git -C "${REPO}" ls-files --cached --others --exclude-standard sim design \
    | grep -vE '^sim/[^/]+/(records|sizing)/' \
    | tar -C "${REPO}" -cf - -T - \
    | tar -C "${sb}" -xf -
  printf '%s' "${sb}"
}

# run_script <sandbox> <script-path-relative-to-sandbox> [args...]
# Runs it with the stubs on PATH and the stub PDK; echoes its exit code.
run_script() {
  local sb="$1" script="$2"; shift 2
  local rc=0
  # shellcheck disable=SC2031
  (
    cd "${sb}"
    PATH="${BIN}:${PATH}" PDK_ROOT="${STUB_PDK}" PDK=ihp-sg13g2 \
      "${sb}/${script}" "$@" >"${TMP}/run.out" 2>"${TMP}/run.err"
  ) || rc=$?
  printf '%s' "${rc}"
}

echo "1. run_klt / run_klt_set exit-code policy (run_klt.sh)"

# Exercise the wrappers directly with a fabricated WORK/REC, which is all they
# need, so the policy is pinned independently of any run script's plumbing.
# policy <rc> <tolerate4> <report:0|1> <stdout-envelope:0|1> <fn:single|set>
policy() {
  local rc="$1" tol="$2" rep="$3" env="$4" fn="$5" out=0
  # PATH/WORK/REC are scoped to this subshell deliberately -- run_klt reads
  # WORK and REC from its caller's environment and must not see the real ones.
  # shellcheck disable=SC2030
  (
    set -euo pipefail
    export PATH="${BIN}:${PATH}"
    export STUB_KLT_SIM_RC="${rc}" STUB_KLT_REPORT="${rep}"
    [[ "${env}" == 1 ]] && export STUB_KLT_SIM_STDOUT='{"requests": []}'
    WORK="$(mktemp -d)"; REC="$(mktemp -d)"; mkdir -p "${REC}/reports"
    # shellcheck source=/dev/null
    source "${REPO}/sim/harness/common/run_klt.sh"
    if [[ "${fn}" == single ]]; then
      run_klt "${WORK}/req.json" probe "${tol}"
    else
      run_klt_set probe "${tol}" "${WORK}/req.json"
    fi
    grep -q 's3://<bucket>' "${REC}/reports/probe.stderr" || exit 90
    rm -rf "${WORK}" "${REC}"
  ) >/dev/null 2>&1 || out=$?
  printf '%s' "${out}"
}

check "single: exit 0 is a result"                        0 "$(policy 0 0 1 0 single)"
check "single: exit 3 is a result"                        0 "$(policy 3 0 1 0 single)"
check "single: exit 4 untolerated is a fleet error"       6 "$(policy 4 0 1 0 single)"
check "single: exit 4 tolerated with a report"            0 "$(policy 4 1 1 0 single)"
check "single: exit 4 tolerated WITHOUT a report"         6 "$(policy 4 1 0 0 single)"
check "single: exit 5 is a fleet error"                   6 "$(policy 5 0 1 0 single)"
check "batch-set: exit 0 is a result"                     0 "$(policy 0 1 0 1 set)"
check "batch-set: exit 3 is a result"                     0 "$(policy 3 1 0 1 set)"
check "batch-set: exit 4 tolerated with an envelope"      0 "$(policy 4 1 0 1 set)"
check "batch-set: exit 4 tolerated WITHOUT an envelope"   6 "$(policy 4 1 0 0 set)"
check "batch-set: exit 4 untolerated"                     6 "$(policy 4 0 0 1 set)"
check "batch-set: exit 5 is a fleet error"                6 "$(policy 5 1 0 1 set)"

echo "2. new_record: append-only guard and directory layout"

# REC/WORK/STAMP are set by new_record inside this subshell on purpose: the
# assertions below are the subshell, so the values never need to escape it.
# shellcheck disable=SC2030,SC2031
if (
  set -euo pipefail
  HERE="${TMP}"   # the trap's scratch pattern is scoped to the caller's HERE
  # shellcheck source=/dev/null
  source "${REPO}/sim/harness/common/setup.sh"
  parent="${TMP}/rec-parent"; mkdir -p "${parent}"
  new_record "${parent}" reports curves
  [[ -d "${REC}/reports" && -d "${REC}/curves" && -d "${WORK}" ]] || exit 91
  [[ "${REC}" == "${parent}/${STAMP}" ]] || exit 92
); then
  pass "new_record creates <parent>/<STAMP> with its subdirectories"
else
  fail "new_record creates <parent>/<STAMP> with its subdirectories"
fi

# The guard fires when the stamp already exists. STAMP is second-resolution, so
# retry if the clock ticks between pre-creating the directory and the call.
guard_rc=""
for _ in 1 2 3; do
  rc=0
  (
    set -euo pipefail
    HERE="${TMP}"
    # shellcheck source=/dev/null
    source "${REPO}/sim/harness/common/setup.sh"
    parent="${TMP}/rec-dup"; mkdir -p "${parent}/$(date -u +%Y%m%dT%H%M%SZ)"
    new_record "${parent}" reports
  ) >/dev/null 2>&1 || rc=$?
  if [[ "${rc}" != 0 ]]; then guard_rc="${rc}"; break; fi
  rm -rf "${TMP}/rec-dup"
done
check "new_record refuses an existing record (append-only)" 4 "${guard_rc}"

echo "3. run script exit codes for each stubbed klt sim outcome"

# A result (0 or 3) must never be reported as the fleet error 6; the scripts go
# on to post-process, which a stub report cannot satisfy, so only "not 6" is
# meaningful there. A fleet error (5) must be 6 from every script.
# submit_ran <sandbox> <sim-subdir>: a redacted stderr inside a fresh record
# directory, which only _klt_finish writes -- so "not 6" cannot pass by the
# script having died before it ever submitted.
submit_ran() {
  local sb="$1" dir="$2"
  grep -rlq 's3://<bucket>' "${sb}/sim/${dir}"/*/*/reports 2>/dev/null
}

for rc in 0 3; do
  for s in bitcell/run_bitcell.sh column/run_column.sh array/run_array.sh column/run_sizing.sh; do
    sb="$(new_sandbox "res")"
    got="$(STUB_KLT_SIM_RC="${rc}" STUB_KLT_REPORT=1 STUB_KLT_SIM_STDOUT='{"requests": []}' \
            run_script "${sb}" "sim/${s}")"
    if [[ "${got}" == 6 ]]; then
      fail "sim/${s}: klt sim exit ${rc} is a result (got fleet error 6)"
    elif ! submit_ran "${sb}" "$(dirname "${s}")"; then
      fail "sim/${s}: klt sim exit ${rc} -- no submit reached run_klt at all"
    else
      pass "sim/${s}: klt sim exit ${rc} is a result (submitted, exit ${got}, not 6)"
    fi
  done
done

for s in bitcell/run_bitcell.sh column/run_column.sh array/run_array.sh column/run_sizing.sh; do
  sb="$(new_sandbox "err")"
  got="$(STUB_KLT_SIM_RC=5 STUB_KLT_REPORT=1 STUB_KLT_SIM_STDOUT='{"requests": []}' \
          run_script "${sb}" "sim/${s}")"
  check "sim/${s}: klt sim exit 5 is a fleet error" 6 "${got}"
done

# Exit 4 with no report/envelope: a fleet error everywhere. run_sizing.sh is
# the behaviour change of issue #157 -- it used to tolerate this unconditionally
# and record a batch error as a sizing result.
for s in bitcell/run_bitcell.sh column/run_column.sh array/run_array.sh column/run_sizing.sh; do
  sb="$(new_sandbox "e4")"
  got="$(STUB_KLT_SIM_RC=4 STUB_KLT_REPORT=0 run_script "${sb}" "sim/${s}")"
  check "sim/${s}: klt sim exit 4 with no report is a fleet error" 6 "${got}"
done

# Exit 4 WITH a report/envelope is a result for the callers that tolerate it.
sb="$(new_sandbox "e4ok")"
got="$(STUB_KLT_SIM_RC=4 STUB_KLT_REPORT=1 STUB_KLT_SIM_STDOUT='{"requests": []}' \
        run_script "${sb}" "sim/column/run_sizing.sh")"
if [[ "${got}" == 6 ]]; then
  fail "sim/column/run_sizing.sh: klt sim exit 4 with an envelope is a result"
elif ! submit_ran "${sb}" column; then
  fail "sim/column/run_sizing.sh: exit 4 with an envelope -- no submit reached run_klt_set"
else
  pass "sim/column/run_sizing.sh: klt sim exit 4 with an envelope is a result (submitted, exit ${got}, not 6)"
fi

echo "4. new_record's trap leaves no scratch request in the checkout"

# Kill each script between two scratch-request writes. The first write has
# landed; the trap set by new_record -- before any write, unlike the inline
# copies it replaces -- must still remove it.
leak_check() { # leak_check <script> <fault-match> <fault-at> <scratch-dir>
  local script="$1" match="$2" at="$3" dir="$4"
  local sb; sb="$(new_sandbox "leak")"
  local rc=0
  # shellcheck disable=SC2031
  (
    cd "${sb}"
    PATH="${BIN}:${PATH}" PDK_ROOT="${STUB_PDK}" PDK=ihp-sg13g2 \
      FAULT_MATCH="${match}" FAULT_AT="${at}" FAULT_COUNT_FILE="${TMP}/fault.count" \
      "${sb}/${script}" >"${TMP}/run.out" 2>"${TMP}/run.err"
  ) || rc=$?
  rm -f "${TMP}/fault.count"
  local left
  left="$(find "${sb}/${dir}" -maxdepth 1 -name '.*.json' -printf '%f\n' 2>/dev/null | sort | tr '\n' ' ')"
  if [[ "${rc}" == 0 ]]; then
    fail "${script}: fault injection did not stop the run"
  elif [[ -n "${left}" ]]; then
    fail "${script}: scratch request(s) left in the checkout: ${left}"
  else
    pass "${script}: no scratch request left after a mid-series failure"
  fi
}

# run_bitcell.sh writes .typ_snm.json then .typ_write.json; fail the second.
leak_check sim/bitcell/run_bitcell.sh "typical-request" 2 sim/bitcell
# run_column.sh writes .req_read.json then .req_write.json; fail the write one
# (the only invocation matching "request write").
leak_check sim/column/run_column.sh "request write" 1 sim/column
# run_array.sh writes .req_snm/.req_write/.req_access.json in a loop.
leak_check sim/array/run_array.sh "request write" 1 sim/array

echo "5. run_smoke.sh (local ngspice, no klt) still runs end to end"

sb="$(new_sandbox "smoke")"
rc=0
# shellcheck disable=SC2031
(
  cd "${sb}"
  PATH="${BIN}:${PATH}" PDK_ROOT="${STUB_PDK}" PDK=ihp-sg13g2 \
    "${sb}/sim/pdk-smoke/run_smoke.sh" >"${TMP}/smoke.out" 2>"${TMP}/smoke.err"
) || rc=$?
check "run_smoke.sh exits 0 against a converging stub ngspice" 0 "${rc}"
rec="$(find "${sb}/sim/pdk-smoke/records" -mindepth 1 -maxdepth 1 -type d | head -1)"
if [[ -n "${rec}" && -f "${rec}/record.json" && -d "${rec}/netlists" && -d "${rec}/logs" ]]; then
  pass "run_smoke.sh writes records/<STAMP>/ with netlists/, logs/ and record.json"
else
  fail "run_smoke.sh writes records/<STAMP>/ with netlists/, logs/ and record.json"
fi
# run_smoke.sh never needs klt: prove it by running with klt off PATH entirely.
rc=0
sb="$(new_sandbox "smoke-noklt")"
NOKLT="${TMP}/bin-noklt"; mkdir -p "${NOKLT}"
cp "${BIN}/ngspice" "${BIN}/python3" "${NOKLT}/"
(
  cd "${sb}"
  PATH="${NOKLT}:/usr/bin:/bin" PDK_ROOT="${STUB_PDK}" PDK=ihp-sg13g2 \
    "${sb}/sim/pdk-smoke/run_smoke.sh" >/dev/null 2>&1
) || rc=$?
check "run_smoke.sh runs with no klt on PATH (sim_setup --no-klt)" 0 "${rc}"

echo "6. sim_setup guards"

sb="$(new_sandbox "guards")"
rc=0
# shellcheck disable=SC2031
(
  cd "${sb}"
  PATH="${BIN}:${PATH}" PDK_ROOT="" PDK=ihp-sg13g2 \
    "${sb}/sim/bitcell/run_bitcell.sh" >/dev/null 2>&1
) || rc=$?
check "unresolved PDK_ROOT stops a batch run" 1 "${rc}"

rc=0
NOTOOL="${TMP}/bin-noklt2"; mkdir -p "${NOTOOL}"; cp "${BIN}/python3" "${NOTOOL}/"
(
  cd "${sb}"
  PATH="${NOTOOL}:/usr/bin:/bin" PDK_ROOT="${STUB_PDK}" PDK=ihp-sg13g2 \
    "${sb}/sim/bitcell/run_bitcell.sh" >/dev/null 2>&1
) || rc=$?
check "klt missing from PATH stops a batch run" 3 "${rc}"

if [[ "${FAILED}" == 0 ]]; then
  echo "test_setup.sh: all checks passed"
else
  echo "test_setup.sh: FAILURES above" >&2
  exit 1
fi

# Sourced by sim_setup (sim/harness/common/setup.sh) unless --no-klt.
#
# The `klt sim` wrappers shared by sim/*/run_*.sh. Batch fleet only: a failed
# submit is reported and the caller exits 6; it never falls back to a local run.
# This file is sourced, not executed, so it has no shebang.
# shellcheck shell=bash

# Fleet capacity policy for a --batch-set submit, stated once. --max-in-flight
# and --capacity-retries are --batch-set-only flags (`klt sim --help`), so they
# have no single-request counterpart to share them with; keeping them here
# means the policy is edited in one place rather than at each call site.
KLT_BATCH_SET_FLAGS=(--max-in-flight 2 --capacity-retries 4)

# KLT_LAST_RC: the raw `klt sim` exit code of the most recent run_klt /
# run_klt_set call, for callers that report it (run_sizing.sh). Only ever 0, 3,
# or a tolerated 4 -- anything else has already exited 6. Read by the sourcing
# script, which shellcheck cannot follow across `source=/dev/null`.
# shellcheck disable=SC2034
KLT_LAST_RC=0

# klt_redact_bucket: stdin -> stdout. Progress lines name the fleet bucket (an
# account id); keep it out of the record.
klt_redact_bucket() { sed -E 's#s3://[^ /]+#s3://<bucket>#g'; }

# _klt_finish <name> <report> <rc> <tolerate_exit4> <what>
# The post-submit policy shared by run_klt and run_klt_set: redact the stderr
# into the record, then decide whether <rc> is a result or a fleet error.
# Exit 0 = all pass, 3 = a measurement limit failed: both are results. Exit 4
# (an errored corner) is a result only when tolerate_exit4 is 1 AND <report>
# exists and is non-empty; anything else is a tool/fleet error: report it and
# exit 6. The report check applies to both submit shapes, so a batch error
# surfacing as exit 4 with no report can never be recorded as a result.
_klt_finish() {
  local name="$1" report="$2" rc="$3" tolerate4="$4" what="$5"
  # shellcheck disable=SC2034  # read by the sourcing script, across source=/dev/null
  KLT_LAST_RC="${rc}"
  klt_redact_bucket < "${WORK}/${name}.stderr" > "${REC}/reports/${name}.stderr"
  if [[ "${rc}" -eq 4 && "${tolerate4}" == 1 && -s "${report}" ]]; then rc=0; fi
  if [[ "${rc}" -ne 0 && "${rc}" -ne 3 ]]; then
    echo "${0##*/}: ${what} failed (exit ${rc}); batch error, no local fallback:" >&2
    tail -5 "${REC}/reports/${name}.stderr" >&2
    exit 6
  fi
}

# run_klt <request> <name> [tolerate_exit4]
# Caller sets WORK (scratch dir) and
# REC (record dir, with reports/ already created).
# Runs the request on the batch fleet; report -> ${REC}/reports/<name>.json.gz,
# redacted stderr -> ${REC}/reports/<name>.stderr, artifacts -> ${WORK}/<name>.
run_klt() {
  local req="$1" name="$2" tolerate4="${3:-0}" rc=0
  klt sim "${req}" --backend batch -o "${WORK}/${name}" \
    --report-out "${REC}/reports/${name}.json.gz" --format json \
    > "${WORK}/${name}.out" 2> "${WORK}/${name}.stderr" || rc=$?
  _klt_finish "${name}" "${REC}/reports/${name}.json.gz" "${rc}" "${tolerate4}" "klt sim ${name}"
}

# run_klt_set <name> <tolerate_exit4> <request> [request ...]
# One `klt sim --batch-set` submit of several independent requests. Caller sets
# WORK and REC as for run_klt. The aggregate JSON envelope is this submit's
# report and lands on stdout, not via --report-out, so it is written to
# ${REC}/reports/<name>.json (plain, not .json.gz); redacted stderr ->
# ${REC}/reports/<name>.stderr, artifacts -> ${WORK}/<name>.
run_klt_set() {
  local name="$1" tolerate4="$2" rc=0
  shift 2
  klt sim --batch-set "$@" "${KLT_BATCH_SET_FLAGS[@]}" \
    -o "${WORK}/${name}" --format json \
    > "${REC}/reports/${name}.json" 2> "${WORK}/${name}.stderr" || rc=$?
  _klt_finish "${name}" "${REC}/reports/${name}.json" "${rc}" "${tolerate4}" "klt sim --batch-set"
}

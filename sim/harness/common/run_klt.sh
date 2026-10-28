# Source me:  source "${SIM_DIR}/harness/common/run_klt.sh"
#
# The one `klt sim` wrapper shared by sim/*/run_*.sh. Batch fleet only: a failed
# submit is reported and the caller exits 6; it never falls back to a local run.
# This file is sourced, not executed, so it has no shebang.
# shellcheck shell=bash

# klt_redact_bucket: stdin -> stdout. Progress lines name the fleet bucket (an
# account id); keep it out of the record.
klt_redact_bucket() { sed -E 's#s3://[^ /]+#s3://<bucket>#g'; }

# run_klt <request> <name> [tolerate_exit4]
# Caller sets WORK (scratch dir) and
# REC (record dir, with reports/ already created).
# Runs the request on the batch fleet; report -> ${REC}/reports/<name>.json.gz,
# redacted stderr -> ${REC}/reports/<name>.stderr, artifacts -> ${WORK}/<name>.
# Exit 0 = all pass, 3 = a measurement limit failed: both are results. Exit 4 (an
# errored corner) is a result only when tolerate_exit4 is 1 AND the report
# exists; anything else is a tool/fleet error: report it and exit 6.
run_klt() {
  local req="$1" name="$2" tolerate4="${3:-0}" rc=0
  klt sim "${req}" --backend batch -o "${WORK}/${name}" \
    --report-out "${REC}/reports/${name}.json.gz" --format json \
    > "${WORK}/${name}.out" 2> "${WORK}/${name}.stderr" || rc=$?
  klt_redact_bucket < "${WORK}/${name}.stderr" > "${REC}/reports/${name}.stderr"
  if [[ "${rc}" -eq 4 && "${tolerate4}" == 1 && -s "${REC}/reports/${name}.json.gz" ]]; then rc=0; fi
  if [[ "${rc}" -ne 0 && "${rc}" -ne 3 ]]; then
    echo "${0##*/}: klt sim ${name} failed (exit ${rc}); batch error, no local fallback:" >&2
    tail -5 "${REC}/reports/${name}.stderr" >&2
    exit 6
  fi
}

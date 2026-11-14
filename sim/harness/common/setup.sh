# Source me:  source "${HERE}/../harness/common/setup.sh"
#
# The setup contract shared by every sim/*/run_*.sh, stated once: path
# resolution (SIM_DIR, REPO), the PDK environment, the tool guards, the
# post-processor handle, the append-only record directory with its cleanup
# trap, and the pinned PDK release tag. Each run script keeps its own HERE,
# its own record parent (records/ vs sizing/), its own subdirectory list, its
# own benches and its own header comment; only the scaffolding is shared.
#
# Diagnostics name the running script with ${0##*/} -- the convention
# run_klt.sh already used -- so no caller passes its own name and no copy can
# fall out of sync with the file it lives in.
#
# This file is sourced, not executed, so it has no shebang; the directive
# below tells shellcheck which dialect to assume.
# shellcheck shell=bash

# SIM_DIR/REPO are resolved from this file's own location, not the caller's, so
# a caller only has to resolve HERE before sourcing. Consumed by the run
# scripts, not by this file.
# shellcheck disable=SC2034
_sim_common_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${_sim_common_dir}/../.." && pwd)"
REPO="$(cd "${SIM_DIR}/.." && pwd)"
unset _sim_common_dir

# sim_setup [--no-klt] [--post <post-script>]
#
#   --no-klt         skip the `klt`-on-PATH guard and do not source run_klt.sh.
#                    sim/pdk-smoke/run_smoke.sh is a local `ngspice -b` check,
#                    not a batch run, and must stay runnable without klt.
#   --post <script>  set POST=(python3 -I "${HERE}/<script>").
#
# Sources env.sh (the PDK resolution shared with design/xschemrc), then
# requires a resolved PDK_ROOT. Callers set HERE before sourcing this file.
# Exit codes are those the run scripts had inline: 1 for an unresolved
# PDK_ROOT (bash's ${var:?} status), 3 for klt missing from PATH.
sim_setup() {
  local want_klt=1 post=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-klt) want_klt=0; shift ;;
      --post)   post="$2"; shift 2 ;;
      *) echo "${0##*/}: sim_setup: unknown argument '$1'" >&2; exit 2 ;;
    esac
  done
  # shellcheck source=/dev/null
  source "${SIM_DIR}/harness/common/env.sh"
  : "${PDK_ROOT:?${0##*/}: no PDK install resolved; see sim/README.md}"
  if [[ "${want_klt}" == 1 ]]; then
    command -v klt >/dev/null || { echo "${0##*/}: klt not on PATH" >&2; exit 3; }
    # shellcheck source=/dev/null
    source "${SIM_DIR}/harness/common/run_klt.sh"
  fi
  if [[ -n "${post}" ]]; then
    POST=(python3 -I "${HERE}/${post}")
  fi
  return 0
}

# new_record <parent-dir> [subdir ...]
#
#   <parent-dir>  the append-only parent to add a record to (records/, sizing/).
#   [subdir ...]  directories to create inside the new record.
#
# Sets STAMP (UTC), REC=<parent-dir>/<STAMP> and WORK (a scratch mktemp dir),
# and installs the EXIT trap that removes WORK together with the caller's
# "${HERE}"/.*.json scratch requests. Exits 4 if the record already exists:
# records are append-only evidence and are never overwritten.
#
# The trap is installed BEFORE the caller writes any scratch request, so a
# failure part-way through a series of writes cannot leave a .json behind in
# the checkout. run_array.sh had this ordering; the copies in run_bitcell.sh
# and run_column.sh trapped WORK first and widened the trap only after their
# scratch writes, so a failure between two writes leaked the first one.
new_record() {
  local parent="$1"; shift
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  REC="${parent}/${STAMP}"
  [[ -e "${REC}" ]] && { echo "${0##*/}: ${REC} exists (records are append-only)" >&2; exit 4; }
  mkdir -p "${REC}"
  local d
  for d in "$@"; do
    mkdir -p "${REC}/${d}"
  done
  WORK="$(mktemp -d)"
  # HERE and WORK are expanded when the trap runs, not now, matching the
  # inline traps this replaces. No sim/*/ directory holds a committed
  # .*.json file, so the pattern only ever names a caller's own scratch
  # request; when it matches nothing `rm -rf` is handed the unexpanded
  # pattern, which does not exist, and -f makes that silent.
  trap 'rm -rf "${WORK}" "${HERE}"/.*.json' EXIT
  return 0
}

# pdk_release_tag: the pinned PDK release tag from sim/pdk.json, on stdout.
# Recorded in every record.json as `pdk_release_tag`.
pdk_release_tag() {
  grep -o '"release_tag": *"[^"]*"' "${SIM_DIR}/pdk.json" | head -1 | cut -d'"' -f4
}

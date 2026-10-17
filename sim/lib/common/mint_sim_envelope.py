#!/usr/bin/env python3
"""sim/lib/mint_sim_envelope.py -- mint the T1 item-5 corner-verification
evidence envelope from the committed append-only corner records.

Issue #128 (T1 item 5, "Full corner verification vs a ratified spec"): the
27-corner PVT sweep exists, passed, and is committed as five append-only
records under sim/*/records/ (per corner: raw measured values), with the
derived sim/signoff-summary.md rendering the per-corner PASS/FAIL rollup --
but none of it was ever minted as a `klt sim` JSON envelope, the only
evidence kind `klt signoff`'s tier-verdict mode accepts for this item.
The sweep cannot simply be *re-run* under `klt sim`: the verb's measurement
contract is ngspice `.meas` cards over a bare circuit body
(docs/cli/sim.md, "Request"), and this block's three binding methodologies
are not expressible as `.meas` cards -- read/hold SNM is a
butterfly-square fit over two independently swept VTC curves
(`sim/lib/snm_extract.py --pair`, Issue #26's two-half-cell derivation)
and write margin is a write-trip bisection search inside the testbench's
own `.control` block (`sim/write-margin/testbench/tb_write_margin.spice`).
Re-running those measurements under `klt sim` would mean abandoning the
ratified methodology, not "minting from records". Per issue #128 this
script therefore *mints* the envelope from the committed records instead:
it transcribes every per-corner value verbatim from the five records (the
same parsing `sim/lib/render_signoff_table.py` already does), applies the
same verdict rule, and stamps the result with the shape `klt signoff`'s
tier-verdict mode recognizes as a `klt sim` envelope
(`measurements[]` + `corner_count`, docs/design-evidence-tiers.md item 5).

Honesty contract, load-bearing, all in the output's `mint` block:

- The envelope **discloses that it was minted, not run**: no `klt_version`
  appears in its provenance (a live `klt sim` report would carry one), and
  the mint block names this renderer, the exact five records each value
  was transcribed from (by committed path + sha256), the verdict rule, and
  why the sweep was not hosted by `klt sim` itself.
- It is a **pure derivation** (like sim/signoff-summary.md and
  measurements/characterization-report.md): reading only committed records,
  running no simulation, embedding no timestamp, and emitting byte-identical
  output for identical inputs -- so CI can (and does, as check 6 in
  scripts/ci/check_evidence_format.py) require the committed envelope to
  match this renderer exactly, the same freshness enforcement checks 4/5
  apply to the other two derivations.
- Its `provenance.input.content_hash` pins the **record aggregate** (the
  sha256 of the five record files' bytes concatenated in this script's
  fixed order) so the signoff manifest can cite it with a content hash the
  grader verifies inside the envelope -- the same pin discipline items
  3/4/7's citations use for their own inputs.

Verdict rule, per `spec/sram.md`'s "### Signoff definition" (the same rule
`sim/lib/render_signoff_table.py` applies):

- read SNM, hold SNM, write margin (write trip voltage): PASS iff the
  recorded value is strictly `> 0` V, at all 27 corners;
- read/write access time: the spec only requires these be *recorded*, so
  a measured value contributes a `reported` measurement (with the slowest
  -- binding -- corner recorded as its worst case), never a failure;
- a corner with no valid measurement (`OPEN` in the record) renders the
  whole envelope `errored` -- it never silently drops.

Usage:
    python3 sim/lib/mint_sim_envelope.py [repo-root] > sim/signoff-sim-envelope.json

Output: the minted envelope as JSON on stdout.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_signoff_table import (  # noqa: E402 (path-injected sibling import)
    CORNER_ORDER,
    latest_record_for_claim,
    parse_record,
)

# The five append-only corner records, in this fixed order: (response
# measurement name, records dir under sim/, Claim substring that finds the
# record, RESULT key inside it, unit, bounded-by-the-Signoff-definition).
# The aggregate input hash concatenates the five files' bytes in this
# order, so the pin is a deterministic function of exactly these files.
ROWS = [
    ("read_snm_v", "read-snm/records", "read SNM", "read_snm_v", "V", True),
    ("hold_snm_v", "hold-snm/records", "hold SNM", "hold_snm_v", "V", True),
    (
        "write_trip_voltage_v",
        "write-margin/records",
        "write margin",
        "write_trip_voltage_v",
        "V",
        True,
    ),
    (
        "read_access_time_s",
        "access-time/records",
        "read access time",
        "read_access_time_s",
        "s",
        False,
    ),
    (
        "write_access_time_s",
        "access-time/records",
        "write access time",
        "write_access_time_s",
        "s",
        False,
    ),
]

#: `spec/sram.md` "### Signoff definition": read SNM, hold SNM, and write
#: margin must be strictly positive at every one of the 27 corners.
LIMIT_MIN = 0.0


def _corner_parts(corner_id: str) -> dict[str, object]:
    """Split `ff_-40c_2.97v` into klt sim's response corner fields."""
    process, temp, vdd = corner_id.replace("c_", "_").split("_")
    return {
        "process": process,
        "supply_v": {"vdd": float(vdd.rstrip("v"))},
        "temperature_c": float(temp),
    }


def main() -> int:
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    sim_dir = repo_root / "sim"

    records: list[dict[str, str]] = []
    per_row_values: dict[str, dict[str, float | None]] = {}
    for name, records_subdir, claim, key, _unit, _bounded in ROWS:
        record_path = latest_record_for_claim(sim_dir / records_subdir, claim)
        records.append(
            {
                "file": record_path.relative_to(repo_root).as_posix(),
                "sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
            }
        )
        parsed = parse_record(record_path)
        per_row_values[name] = {
            corner: (vals.get(key) if isinstance(vals, dict) else None)
            for corner, vals in parsed.items()
        }

    # The aggregate input pin: sha256 over the five record files' bytes,
    # concatenated in ROWS order -- a deterministic function of exactly the
    # files whose values the envelope transcribes.
    aggregate = hashlib.sha256()
    for record in records:
        aggregate.update((repo_root / record["file"]).read_bytes())
    aggregate_hash = f"sha256:{aggregate.hexdigest()}"

    measurements_rollup: list[dict[str, object]] = []
    corners: list[dict[str, object]] = []
    errored = 0

    for corner_id in CORNER_ORDER:
        corner_measurements: list[dict[str, object]] = []
        corner_status = "pass"
        for name, _sub, _claim, _key, unit, bounded in ROWS:
            value = per_row_values[name].get(corner_id)
            entry: dict[str, object] = {"name": name, "unit": unit}
            if value is None:
                # A corner with no valid measurement for this row: an OPEN
                # record result renders this corner errored, never dropped.
                entry.update({"value": None, "status": "error"})
                corner_status = "error"
                errored += 1
            elif bounded:
                status = "pass" if value > LIMIT_MIN else "fail"
                entry.update(
                    {"value": value, "status": status, "margin": value - LIMIT_MIN}
                )
                if status == "fail" and corner_status != "error":
                    corner_status = "fail"
            else:
                # spec/sram.md only requires access times be recorded: a
                # measured value is reported, never compared against a
                # threshold (the same rule render_signoff_table.py applies).
                entry.update({"value": value, "status": "reported"})
            corner_measurements.append(entry)
        corners.append(
            {
                "corner_id": corner_id,
                **_corner_parts(corner_id),
                "status": corner_status,
                "measurements": corner_measurements,
                "diagnostics": [],
                "artifacts": {
                    "log": None,
                    "raw": None,
                    "waveform": None,
                    "deck": None,
                },
            }
        )

    failed = sum(1 for c in corners if c["status"] == "fail")
    status = "error" if errored else ("fail" if failed else "pass")

    for name, _sub, _claim, _key, unit, bounded in ROWS:
        entries = {
            c["corner_id"]: next(
                m for m in c["measurements"] if m["name"] == name
            )
            for c in corners
        }
        row_open = any(e["status"] == "error" for e in entries.values())
        measurement: dict[str, object] = {
            "name": name,
            "unit": unit,
        }
        if bounded:
            measurement["limits"] = {"min": LIMIT_MIN}
            binding_id, binding = min(
                entries.items(), key=lambda kv: kv[1]["value"]
            )
            measurement["worst_case"] = {
                "corner_id": binding_id,
                "value": binding["value"],
                "margin": binding["value"] - LIMIT_MIN,
            }
            measurement["status"] = (
                "error" if row_open else binding["status"]
            )
        else:
            measurement["status"] = "error" if row_open else "reported"
            # For a recorded-only row the *slowest* corner is the binding
            # one -- the corner an access-time spec limit would bind first.
            slowest_id, slowest = max(
                (
                    (cid, e)
                    for cid, e in entries.items()
                    if e["value"] is not None
                ),
                key=lambda kv: kv[1]["value"],
            )
            measurement["slowest_case"] = {
                "corner_id": slowest_id,
                "value": slowest["value"],
            }
            measurement["note"] = (
                "spec/sram.md requires this row be recorded, not bounded -- "
                "no pass/fail verdict applies; the slowest corner is "
                "recorded as the binding case"
            )
        measurements_rollup.append(measurement)

    envelope: dict[str, object] = {
        "schema_version": 3,
        "status": status,
        "corner_count": len(corners),
        "passed": sum(1 for c in corners if c["status"] == "pass"),
        "failed": failed,
        "errored": errored,
        "metrics": {
            "sim__corner__count": len(corners),
            "sim__corner__passed_count": sum(
                1 for c in corners if c["status"] == "pass"
            ),
            "sim__corner__failed_count": failed,
            "sim__corner__errored_count": errored,
        },
        "mint": {
            "minted_by": "sim/lib/mint_sim_envelope.py",
            "disclosure": (
                "Minted from the committed append-only corner records below, "
                "NOT produced by a live `klt sim` ngspice sweep. This block's "
                "three binding methodologies are not expressible as ngspice "
                ".meas cards over a bare circuit body (read/hold SNM is a "
                "butterfly-square fit over two independently swept VTC "
                "curves, sim/lib/snm_extract.py --pair; write margin is a "
                "write-trip bisection inside the testbench's own .control "
                "block), so the ratified sweep runner "
                "sim/lib/run_corner_sweep.sh cannot be hosted by the verb. "
                "Every value below is transcribed verbatim from the named "
                "records; re-run those methodologies under a future `klt "
                "sim` able to host them and retire this mint."
            ),
            "verdict_rule": (
                "spec/sram.md '### Signoff definition' -- the same rule "
                "sim/lib/render_signoff_table.py applies: read SNM, hold SNM, "
                "and write margin PASS iff strictly > 0 V at all 27 corners; "
                "read/write access time are recorded only, never bounded."
            ),
            "recorded_from": records,
        },
        "provenance": {
            "input": {"content_hash": aggregate_hash, "role": "corner-records"},
            "note": (
                "no klt_version here on purpose: no klt invocation produced "
                "this envelope (see the mint block); the input pin is the "
                "sha256 of the five record files' bytes concatenated in "
                "mint.recorded_from order"
            ),
        },
        "measurements": measurements_rollup,
        "corners": corners,
    }

    json.dump(envelope, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the #230 write-margin cost pilot on the batch fleet. See README.md."""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from bitcell_post import BL_STEP_V, cmd_write, searched_margin

HERE = Path(__file__).resolve().parent

REFERENCE = HERE / "records/20261023T231238Z"
SIZES = (10, 30)
METHODS = {"sweep": "request_write_mc.json", "search": "request_write_search.json"}


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def requests(directory):
    paths = []
    for method, template in METHODS.items():
        request = read(HERE / template)
        request["netlist"] = os.path.relpath(HERE / request["netlist"], directory)
        for n in SIZES:
            request["monte_carlo"]["n"] = n
            path = directory / f"{method}_{n}.json"
            write(path, request)
            paths.append(path)
        if method == "search":
            del request["monte_carlo"]
            request["corners"]["process"] = ["mos_tt"]
            for point in ("typical", "grid"):
                if point == "grid":
                    request["corners"] = read(HERE / "request_write.json")["corners"]
                path = directory / f"{point}.json"
                write(path, request)
                paths.append(path)
    return paths


def check_equivalence(report, point):
    reference = read(REFERENCE / f"{point}_write.json")
    grid = {c["corner_id"]: c["write_margin_v"] for c in reference["corners"]}
    comparisons = []
    for corner in report["corners"]:
        cid = corner["corner_id"]
        old = grid.pop(cid)
        value = searched_margin(corner)
        # The old grid reports the highest passing level. A true threshold
        # between it and the next level is consistent with that observation.
        search = next(
            m["search"] for m in corner["measurements"] if m["name"] == "write_margin_v"
        )
        if search["converged"]:
            agrees = (
                old is not None
                and search["hi"] >= old
                and search["lo"] < old + BL_STEP_V
            )
        else:
            agrees = old == value
        comparisons.append(
            {
                "corner_id": cid,
                "grid_v": old,
                "search_v": value,
                "bracket": search,
                "agrees": agrees,
            }
        )
    if grid:
        raise ValueError(f"missing deterministic corners: {sorted(grid)}")
    return comparisons


def sample_cost(path, request, method):
    report = read(path)
    mc = request["monte_carlo"]
    actual = report["environment"]["monte_carlo"]
    if any(actual[key] != value for key, value in mc.items()) or not any(
        f["family"] == "mosfet" and f["active"] is True
        for f in actual["family_mismatch"]
    ):
        raise ValueError("fleet report does not match the requested mismatch draw")
    corners = report["corners"]
    n = mc["n"]
    if any(
        c["process"] != "mos_tt_mismatch"
        or c["temperature_c"] != 27
        or c["supply_v"] != {"vdd": 1.2}
        for c in corners
    ):
        raise ValueError("expected the typical pilot point")
    if sorted(c["monte_carlo"]["sample_index"] for c in corners) != list(range(n)):
        raise ValueError(f"missing or duplicate draws in {path}")
    if method == "sweep":
        grid = cmd_write(str(path), "pilot")["corners"]
        if any(c["klt_status"] != "pass" or not c.get("monotonic") for c in grid):
            raise ValueError(f"unresolved or non-monotonic sweep in {path}")
        values = [c["write_margin_v"] for c in grid]
    else:
        values = [searched_margin(c) for c in corners]
    samples = []
    for corner, margin in zip(corners, values, strict=True):
        runtime = corner["runtime_s"]
        if not math.isfinite(runtime) or runtime <= 0:
            raise ValueError(f"missing engine time for {corner['corner_id']}")
        samples.append(
            {
                "corner_id": corner["corner_id"],
                **corner["monte_carlo"],
                "write_margin_v": margin,
                "runtime_s": runtime,
            }
        )
    remote = report["environment"]["remote"]
    jobs = remote.get("fleet", [remote])
    start = min(datetime.fromisoformat(j["client_submitted_at"]) for j in jobs)
    end = max(datetime.fromisoformat(j["client_collected_at"]) for j in jobs)
    hours = sum(s["runtime_s"] for s in samples) / 3600
    cost = {
        **mc,
        "unit_count": len(samples),
        "wall_s": (end - start).total_seconds(),
        "unit_hours": hours,
        "unit_hours_per_sample": hours / n,
        "jobs": [
            {
                k: j[k]
                for k in (
                    "job_id",
                    "runner_klt_version",
                    "client_submitted_at",
                    "client_collected_at",
                )
            }
            for j in jobs
        ],
        "samples": samples,
    }
    numeric = [v for v in values if v is not None]
    sample_set = {
        "measurements": [
            {
                "name": "write_margin_v",
                "unit": "V",
                "samples": numeric,
                "failed_unmeasurable": n - len(numeric),
                "limits": {"min": 0.0, "exclusive_min": True},
            }
        ]
    }
    return cost, sample_set


def projections(runs):
    # Use the larger run for the extrapolation (the same seed is reused, so
    # the n=10 run is a prefix and must not be pooled as independent draws).
    rates = {m: runs[f"{m}_30"]["unit_hours_per_sample"] for m in METHODS}
    lines = [
        "Write-margin cost pilot at mos_tt_mismatch, 1.20 V, 27 °C.",
        "These sample counts are too small for item 6 yield evidence.",
        "",
        "| Method | n | Units | Wall s | Engine unit-h/sample |",
        "|---|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        for n in SIZES:
            run = runs[f"{method}_{n}"]
            lines.append(
                f"| {method} | {n} | {run['unit_count']} | {run['wall_s']:.2f} | "
                f"{run['unit_hours_per_sample']:.7f} |"
            )
    lines.extend(
        [
            "",
            (
                "Projected write-margin engine unit-hours using the n=30 rates. "
                "Assumes the typical mean engine time per draw at every corner. "
                "The four points are typical, FS/1.08 V/125 °C, SF/1.08 V/−40 °C "
                "and FF/1.08 V/125 °C."
            ),
            "",
            "| Corners | n per corner | Sweep unit-h | Search unit-h |",
            "|---|---:|---:|---:|",
        ]
    )
    for points in (4, 45):
        for n in (100, 300, 1000):
            lines.append(
                f"| {points} | {n} | {points * n * rates['sweep']:.5f} | {points * n * rates['search']:.5f} |"
            )
    return "\n".join(lines) + "\n"


def run(work, dry_run):
    paths = requests(work)
    cmd = [
        "klt",
        "sim",
        "--batch-set",
        *paths,
        "--max-in-flight",
        "2",
        "--capacity-retries",
        "4",
        "--wait-for-capacity",
        "600",
        "--format",
        "json",
        "-o",
        work / "jobs",
    ]
    if dry_run:
        subprocess.run([*cmd, "--dry-run"], check=True)
        return
    proc = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, text=True)
    (work / "batch-set.json").write_text(proc.stdout)
    if proc.returncode not in (0, 3, 4):
        raise RuntimeError(proc.stdout.strip() or f"klt sim exited {proc.returncode}")
    members = json.loads(proc.stdout)["requests"]
    if sorted(Path(m["request"]) for m in members) != sorted(paths):
        raise ValueError("batch-set returned an incomplete or unexpected request set")
    for member in members:
        if member["error"] or not member["report"]:
            raise RuntimeError(f"{member['request']}: {member['error']}")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    record = work / "record"
    record.mkdir()
    runs = {}
    comparisons = []
    for member in members:
        request = Path(member["request"])
        path = Path(member["report"])
        name = request.stem
        if name in ("grid", "typical"):
            comparisons.extend(check_equivalence(read(path), name))
            continue
        method = name.split("_")[0]
        runs[name], samples = sample_cost(path, read(request), method)
        sample_set = record / f"{name}_samples.json"
        write(sample_set, samples)
        result = subprocess.run(
            ["klt", "yield", sample_set, "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"klt yield {name}: {result.stderr or result.stdout}")
        write(record / f"{name}_yield.json", json.loads(result.stdout))
    write(record / "deterministic.json", comparisons)
    write(
        record / "write_pilot.json",
        {
            "purpose": "Write-margin cost pilot only. Sample sizes are too small for item 6 yield evidence.",
            "corner": "mos_tt_mismatch/1.200V/27C",
            "klt_client": "0.9.2",
            "pdk_release": read(HERE.parent / "pdk.json")["release_tag"],
            "grid_step_v": BL_STEP_V,
            "search_tolerance_v": 0.00625,
            "runs": runs,
        },
    )
    equivalent = all(c["agrees"] for c in comparisons)
    if equivalent:
        (record / "projection.md").write_text(projections(runs))
    published = HERE / "records" / stamp
    shutil.copytree(record, published)  # fails if another run already used this stamp
    print(f"Pilot record: {published}", flush=True)
    if not equivalent:
        raise ValueError(
            f"deterministic comparison failed, see {published}/deterministic.json"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the batch set without submitting",
    )
    args = parser.parse_args()
    if subprocess.check_output(["klt", "--version"], text=True).strip() != "klt 0.9.2":
        sys.exit("activate an environment with klayout-tools[yield]==0.9.2")
    work = Path(tempfile.mkdtemp(prefix="write-pilot-"))
    print(f"Pilot batch requests and raw reports: {work}", file=sys.stderr, flush=True)
    run(work, args.dry_run)
    shutil.rmtree(work)  # keep the original reports if processing or collection fails

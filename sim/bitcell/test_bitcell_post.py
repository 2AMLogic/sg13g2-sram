#!/usr/bin/env python3
"""Tests for bitcell SNM, write-margin extraction and pilot cost accounting.

Run: python3 sim/bitcell/test_bitcell_post.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bitcell_post  # noqa: E402
import run_write_pilot  # noqa: E402


def step_vtc(vm: float, w: float, n: int = 201):
    """Near-ideal inverter on [0, 1]: 1 below vm, 0 above, linear across 2w."""
    pts = []
    for i in range(n):
        x = i / (n - 1)
        y = 1.0 if x <= vm - w else 0.0 if x >= vm + w else (vm + w - x) / (2 * w)
        pts.append((x, y))
    return pts


def main() -> int:
    ideal = step_vtc(0.5, 0.005)
    sq = bitcell_post.signed_snm(ideal, ideal)[0]
    assert sq is not None and abs(sq - 0.5) < 0.02, sq  # two 0.5 x 0.5 eyes
    # the vertical-gap method of snm_extract.py over-reads the square
    import snm_extract
    vgap = min(snm_extract.snm(ideal, ideal))
    assert vgap > sq, (vgap, sq)
    # a gain < 1 inverter pair is monostable: no eyes, caller falls back
    flat = [(i / 100, 1.0 - 0.2 * (i / 100) - 0.4) for i in range(101)]
    assert bitcell_post.signed_snm(flat, flat)[0] < 0
    # a weaker, skewed pair (switch point 0.4 / 0.6) shrinks the smaller eye
    skew = bitcell_post.square_snm(step_vtc(0.4, 0.005), step_vtc(0.6, 0.005))
    assert skew is not None and skew < sq, skew
    test_search_margin()
    test_pilot_cost()
    print("ok")
    return 0


def test_search_margin():
    # klt returns the midpoint, but both endpoint outcomes also matter when
    # no threshold lies in [0, 0.8] V. A solver failure must stop the pilot.
    search = {"name": "write_margin_v", "value": 0.403125, "status": "pass",
              "search": {"lo": 0.4, "hi": 0.40625, "converged": True}}
    endpoint = {"name": "zero_score", "value": -1.2, "status": "pass"}
    corner = {"corner_id": "typical", "measurements": [search, endpoint],
              "status": "pass", "diagnostics": []}
    assert bitcell_post.searched_margin(corner) == 0.403125
    search.update(value=None, status="error", search={"converged": False})
    corner.update(status="error", diagnostics=[
        {"code": "measurement", "severity": "error", "message": "[search_bracket_invalid] same endpoints"}
    ])
    assert bitcell_post.searched_margin(corner) == 0.8
    endpoint["value"] = 0
    assert bitcell_post.searched_margin(corner) is None
    corner["diagnostics"][0]["message"] = "[search_probe_failed] missing vector"
    try:
        bitcell_post.searched_margin(corner)
    except ValueError:
        pass
    else:
        raise AssertionError("solver failure treated as a physical margin")


def test_pilot_cost():
    mc = {"n": 2, "vary": "mismatch", "seed": 42}
    point = {"process": "mos_tt_mismatch", "temperature_c": 27, "supply_v": {"vdd": 1.2}}
    corners = [
        {**point, "corner_id": f"mos_tt_mismatch/1.200V/27C/mc{i}", "status": "pass",
         "monte_carlo": {"sample_index": i}, "runtime_s": 3.6, "diagnostics": [],
         "measurements": [{"name": f"d_{instant}_{k}", "value": -1 if k < i else 1}
                          for instant in ("end", "fin") for k in range(33)]}
        for i in range(2)
    ]
    jobs = [{"job_id": str(i), "runner_klt_version": "0.9.2",
             "client_submitted_at": f"2026-11-20T12:00:0{i}Z",
             "client_collected_at": f"2026-11-20T12:00:1{i}Z"} for i in range(2)]
    report = {"corners": corners, "environment": {"remote": {"fleet": jobs},
              "monte_carlo": {**mc, "family_mismatch": [{"family": "mosfet", "active": True}]}}}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.json"
        run_write_pilot.write(path, report)
        cost, sample_set = run_write_pilot.sample_cost(path, {"monte_carlo": mc}, "sweep")
        assert cost["wall_s"] == 11
        assert cost["unit_hours_per_sample"] == 0.001
        assert cost["unit_count"] == 2
        row = sample_set["measurements"][0]
        assert row["samples"] == [0.0] and row["failed_unmeasurable"] == 1
        assert row["limits"] == {"min": 0.0, "exclusive_min": True}


if __name__ == "__main__":
    raise SystemExit(main())

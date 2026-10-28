#!/usr/bin/env python3
"""Tests for sim/array/array_post.py (pure Python, no simulator).

Run: python3 -I sim/array/test_array_post.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import array_post as ap  # noqa: E402

REPO = HERE.parent.parent


def write_meas(trip_top: int, ldrv: float = 0.05, flip_abs_ns: float = 1.08, **over) -> dict:
    """Measurement dict of the write bench: trip cells 0..trip_top flip."""
    m = {}
    for k in range(ap.N_LEVELS):
        d = -1.1 if k <= trip_top else 1.1
        m[f"d_end_{k}"], m[f"d_fin_{k}"] = d, d
    for c, sign in (("c", -1), ("d", 1)):
        m.update({f"fl_{c}": sign * 1.1, f"ff_{c}": sign * 1.2, f"ldrv_{c}": ldrv,
                  f"tf_{c}": flip_abs_ns * 1e-9, f"hs_{c}": sign * 1.2})
    m.update(over)
    return m


def test_write_margin_positive_and_worst_case():
    v = ap.verdict_write(write_meas(trip_top=12))          # trip level 0.300 V
    assert v["trip_level_v"] == 0.3
    assert all(abs(cs["margin_v"] - 0.25) < 1e-9 for cs in v["cases"].values())
    assert v["write_margin_v"] == 0.25 and v["pass"], v
    assert abs(v["cases"]["c"]["flip_time_ns"] - 0.07) < 1e-9
    # asymmetric drivers: the margin reported is the worse of the two
    m = write_meas(12, ldrv_d=0.2)
    assert abs(ap.verdict_write(m)["write_margin_v"] - 0.1) < 1e-9


def test_write_margin_not_positive_is_counted():
    v = ap.verdict_write(write_meas(trip_top=12, ldrv=0.32))   # driver does not reach the trip level
    assert not v["pass"] and v["write_margin_v"] < 0
    v = ap.verdict_write(write_meas(trip_top=-1))             # no cell flips even at 0 V
    assert v["trip_level_v"] is None and v["write_margin_v"] is None and not v["pass"]
    assert "not positive" in v["note"]


def test_write_missing_measurement_fails():
    m = write_meas(12)
    del m["d_end_3"]
    v = ap.verdict_write(m)
    assert not v["pass"] and "error" in v
    m = write_meas(12, tf_c=None)                             # driver never flips the cell
    v = ap.verdict_write(m)
    assert not v["pass"] and v["cases"]["c"]["flip_time_ns"] is None and not v["cases"]["c"]["flipped_within_pulse"]


def test_write_slower_than_pulse_fails():
    v = ap.verdict_write(write_meas(12, flip_abs_ns=2.2))
    assert not v["cases"]["c"]["flipped_within_pulse"] and not v["pass"]


def access_meas(**over) -> dict:
    m = {"vdd_check": 1.2, "tclk_read1b": 44.05e-9, "tclk_read0": 28.05e-9, "tclk_write1": 4.05e-9, "tclk_write0": 20.05e-9,
         "tq_read1b": 45.2e-9, "tq_read0": 29.3e-9, "qend_read1": 1.2, "qend_read0": 0.0, "qend_read1b": 1.2,
         "tflip_write1": 5.0e-9, "tflip_write0": 21.0e-9, "twl_rise_write1": 4.5e-9, "twl_rise_write0": 20.5e-9,
         "cell_after_write1": 1.2, "cell_after_write0": -1.2}
    m.update(over)
    return m


def test_access_times():
    v = ap.verdict_access(access_meas())
    assert v["pass"], v
    assert abs(v["read1_access_ns"] - 1.15) < 1e-6 and abs(v["read0_access_ns"] - 1.25) < 1e-6
    assert abs(v["write1_flip_after_clk_ns"] - 0.95) < 1e-6 and abs(v["write1_flip_after_wl_ns"] - 0.5) < 1e-6


def test_access_failing_cases_are_counted():
    v = ap.verdict_access(access_meas(tq_read1b=None, qend_read1b=0.0))   # Q never reaches 90 %
    assert not v["pass"] and not v["checks"]["read1_valid"] and v["checks"]["read0_valid"]
    v = ap.verdict_access(access_meas(qend_read1=0.0))                    # the first read returned the wrong value
    assert not v["checks"]["read1_valid"]
    v = ap.verdict_access(access_meas(tflip_write0=None))                 # cell never flips
    assert not v["pass"] and not v["checks"]["write0_completed"]
    v = ap.verdict_access(access_meas(qend_read0=0.5))                    # Q settles mid-rail
    assert not v["checks"]["read0_valid"]
    assert not ap.verdict_access({"vdd_check": 1.2})["pass"]              # missing measurements


def test_access_timeline_is_consistent():
    # every measurement window opens before the edge it measures and the run ends after the last cycle
    assert list(ap.ACCESS_EDGES_NS) == ap.ACCESS_CYCLES
    edges = list(ap.ACCESS_EDGES_NS.values())
    assert all(b - a == ap.ACCESS_PERIOD_NS for a, b in zip(edges, edges[1:]))
    assert ap.ACCESS_T_STOP_NS == edges[-1] + ap.ACCESS_PERIOD_NS
    names = [x["name"] for x in ap.access_measurements()]
    assert len(names) == len(set(names))


def test_requests():
    grid = ap.make_request("write")
    assert len(grid["corners"]["process"]) * len(grid["corners"]["supply_v"]["vdd"]) * len(grid["corners"]["temperature_c"]) == 45
    typ = ap.make_request("access", typical=True)
    assert typ["corners"] == {"process": ["mos_tt"], "supply_v": {"vdd": [1.2]}, "temperature_c": [25]}
    names = [m["name"] for m in grid["measurements"]]
    assert len(names) == len(set(names)) and "d_fin_32" in names
    assert ap.make_request("snm")["analysis"]["kind"] == "dc"


def test_committed_benches_match_their_sources():
    text = ap.gen_access(str(REPO / "design/macro/macro.spice"))
    assert (HERE / "bench_access.cir").read_text() == text, "bench_access.cir is stale: array_post.py gen-access"
    # every measurement node the bench is read through exists in the bench
    for net in ("q0m", "clkm", "thr9", "thr5", "thr1", "wl45m", "cq", "cqb"):
        assert f" {net} " in text, net
    wb = (HERE / "bench_write.cir").read_text()
    for k in range(ap.N_LEVELS):
        assert f"Xt{k} bl{k} vdd wl vdd 0 q{k} qb{k} bitcell" in wb
        assert f"Vbl{k} bl{k} 0 DC {0.025 * k:.3f}" in wb


def test_weaken():
    col = (REPO / "design/column/column.spice").read_text()
    snm = ap.weaken(col, "snm")
    assert snm != col and snm.count("w=0.15u") >= 2 and "w=0.60u" in snm
    wr = ap.weaken(col, "write")
    assert wr != col and "w=0.15u" in wr and wr.count("w=3.0u") < col.count("w=3.0u")


def test_negctl_bench_includes_resolve():
    with tempfile.TemporaryDirectory() as d:
        dst = Path(d) / "sub" / "b.cir"
        dst.parent.mkdir()
        ap.cmd_negctl_bench(str(HERE / "bench_snm.cir"), str(dst), {"column.spice": "./column_weak.spice"})
        assert ".include ./column_weak.spice" in dst.read_text()
        ap.cmd_negctl_bench(str(HERE / "bench_snm.cir"), str(dst), {})
        inc = [l for l in dst.read_text().splitlines() if l.startswith(".include")][0].split()[1]
        assert (dst.parent / inc).resolve() == (REPO / "design/column/column.spice").resolve()


def test_snm_of_ideal_curves_through_report_path():
    fin = ap._finish({"corners": [{"corner_id": "a", "pass": True}, {"corner_id": "b", "pass": False}]})
    assert fin["failing_corners"] == ["b"] and fin["any_fail"] and fin["corner_count"] == 2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)

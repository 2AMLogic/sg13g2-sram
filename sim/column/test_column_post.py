#!/usr/bin/env python3
"""Tests for sim/column/column_post.py (pure Python, no simulator).

Run: python3 -I sim/column/test_column_post.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import column_post as cp  # noqa: E402


def good_read() -> dict:
    m = {}
    for c, (_, s) in cp.READ_CASES.items():
        e = 1 if s else -1
        m.update({f"rd_{c}": e * 1.19, f"eq_{c}": 0.001, f"eq1_{c}": -0.002, f"pre_{c}": 1.199,
                  f"dbl_{c}": e * 0.2, f"ret_{c}": e * 0.9, f"hs_{c}": -e * 0.9, f"hsbl_{c}": 1.0})
    return m


def good_write() -> dict:
    m = {}
    for c, (_, s) in cp.WRITE_CASES.items():
        w = -1 if s else 1
        m.update({f"fl_{c}": w * 1.0, f"ff_{c}": w * 1.2, f"hs_{c}": (1 if s == 0 else -1) * 0.9,
                  f"blw_{c}": 0.5, f"tf_{c}": 0.6e-9, f"hsbl_{c}": 1.0})
    return m


def main() -> int:
    v = cp.verdict_read(good_read())
    assert all(c["pass"] for c in v.values()), v
    # sense amp resolving the wrong value is caught (negative control for the read bench)
    bad = good_read(); bad["rd_a"] = -1.19
    assert not cp.verdict_read(bad)["a"]["pass"] and cp.verdict_read(bad)["b"]["pass"]
    # an unresolved latch (metastable) is caught
    bad = good_read(); bad["rd_b"] = 0.05
    assert not cp.verdict_read(bad)["b"]["checks"]["sense_resolves_stored_value"]
    # missing measurement is a failure, not a pass
    bad = good_read(); del bad["rd_a"]
    assert not cp.verdict_read(bad)["a"]["pass"]

    w = cp.verdict_write(good_write())
    assert all(c["pass"] for c in w.values()), w
    assert abs(w["c"]["flip_time_ns"] - (0.6 - cp.T_WL_MID_NS)) < 1e-6
    # an undersized driver: cell does not flip within the pulse
    bad = good_write(); bad["fl_c"] = 0.9; bad["ff_c"] = 0.9; bad["tf_c"] = None
    assert not cp.verdict_write(bad)["c"]["pass"] and cp.verdict_write(bad)["d"]["pass"]
    # a flip that happens after the pulse is not a pass
    bad = good_write(); bad["tf_d"] = 2.0e-9
    assert not cp.verdict_write(bad)["d"]["checks"]["flipped_within_1ns_pulse"]

    for kind in ("read", "write"):
        r = cp.make_request(kind)
        names = [m["name"] for m in r["measurements"]]
        assert len(names) == len(set(names)) and r["corners"]["process"] == ["mos_tt"]

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "neg" / "bench_read.cir"
        out.parent.mkdir()
        cp.cmd_negctl_bench(str(HERE / "bench_read.cir"), str(out),
                            {"write_driver.spice": "./wd_weak.spice"}, "0.8")
        t = out.read_text()
        assert ".include ./wd_weak.spice" in t and "PULSE(0 1.2 0.8n" in t.split("Vsae")[1]
        assert ".include ../../design/" not in t       # re-pointed relative to the new directory
        assert (out.parent / t.split(".include ")[1].split()[0]).resolve().exists()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

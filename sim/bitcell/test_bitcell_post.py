#!/usr/bin/env python3
"""Tests for sim/bitcell/bitcell_post.py's inscribed-square SNM (pure Python).

Run: python3 sim/bitcell/test_bitcell_post.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bitcell_post  # noqa: E402


def step_vtc(vm: float, w: float, n: int = 201):
    """Near-ideal inverter on [0, 1]: 1 below vm, 0 above, linear across 2w."""
    pts = []
    for i in range(n):
        x = i / (n - 1)
        y = 1.0 if x <= vm - w else 0.0 if x >= vm + w else (vm + w - x) / (2 * w)
        pts.append((x, y))
    return pts


def test_monte_carlo() -> None:
    import json
    import tempfile

    # negative control: "clearly below" means a mean gap above 3 sigma, not mere ordering
    ref = [0.20, 0.21, 0.19, 0.205, 0.195]
    assert bitcell_post.negctl_detected(ref, [0.12, 0.13, 0.11, 0.125, 0.115])
    assert not bitcell_post.negctl_detected(ref, [0.19, 0.20, 0.18, 0.195, 0.185])  # overlapping
    assert not bitcell_post.negctl_detected(ref, [0.5, 0.5, 0.5, 0.5, 0.5])  # above, not below
    assert not bitcell_post.negctl_detected(ref, [0.1])  # too few samples

    # sample set: strictly positive limit; a failing or valueless sample is counted, never dropped
    snm = {"samples": [{"hold_snm_v": 0.4, "read_snm_v": 0.2}, {"hold_snm_v": 0.4, "read_snm_v": -0.01},
                       {"hold_snm_v": 0.4, "read_snm_v": None}, {"corner_id": "x", "error": "boom"}]}
    wr = {"samples": [{"write_margin_v": 0.25}, {"write_margin_v": 0.0}, {"write_margin_v": None}]}
    ys = {m["name"]: m for m in bitcell_post.yield_set(snm, wr)["measurements"]}
    assert ys["read_snm_v"]["samples"] == [0.2, -0.01]
    assert ys["read_snm_v"]["failed_unmeasurable"] == 1 and ys["read_snm_v"]["errored"] == 1
    assert ys["read_snm_v"]["limits"] == {"min": 0.0, "exclusive_min": True}
    assert ys["write_margin_v"]["samples"] == [0.25, 0.0] and ys["write_margin_v"]["failed_unmeasurable"] == 1

    # same seed => identical samples; any difference is detected
    a = {"samples": [{"read_snm_v": 0.2, "hold_snm_v": 0.4}]}
    assert bitcell_post.same_samples(a, json.loads(json.dumps(a)))
    assert not bitcell_post.same_samples(a, {"samples": [{"read_snm_v": 0.2000001, "hold_snm_v": 0.4}]})
    assert not bitcell_post.same_samples({"samples": []}, {"samples": []})

    # request writer: mismatch section + monte_carlo block; n = 0 is the deterministic request
    with tempfile.TemporaryDirectory() as d:
        base, out = f"{d}/b.json", f"{d}/o.json"
        json.dump({"corners": {}, "monte_carlo": {"n": 1}}, open(base, "w"))
        bitcell_post.cmd_mc_request(base, out, "mos_fs", 1.08, 125, 300, 7, None)
        r = json.load(open(out))
        assert r["corners"]["process"] == ["mos_fs_mismatch"] and r["monte_carlo"] == {"n": 300, "seed": 7, "vary": "mismatch"}
        bitcell_post.cmd_mc_request(base, out, "mos_fs_mismatch", 1.08, 125, 0, 0, None)
        r = json.load(open(out))
        assert r["corners"]["process"] == ["mos_fs"] and "monte_carlo" not in r


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
    test_monte_carlo()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

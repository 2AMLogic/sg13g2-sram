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
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
